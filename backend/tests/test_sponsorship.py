"""resolve_sponsorship() is the plan §6 6-rule decision matrix.
These tests are the executable spec of how Nexus combines a JD-text signal
with LCA filing history into a final visa verdict. Any future tweak to the
rule ordering should adjust these tests + the docstring in services/sponsorship.py
in the same commit.
"""
import pytest

from services.sponsorship import (
    SponsorshipVerdict,
    parse_classifier_output,
    resolve_sponsorship,
)


def _call(
    *,
    jd_status="unclear",
    jd_confidence=0.5,
    jd_evidence="",
    cpt_opt=False,
    lca_count_12mo=None,
    lca_year=None,
) -> SponsorshipVerdict:
    """Test helper — names the resolver's arguments and supplies defaults."""
    return resolve_sponsorship(
        jd_status=jd_status,
        jd_confidence=jd_confidence,
        jd_evidence=jd_evidence,
        cpt_opt_signal=cpt_opt,
        lca_count_12mo=lca_count_12mo,
        lca_most_recent_year=lca_year,
    )


# ---- Rule 1: explicit JD denial overrides ANY LCA history ----


def test_no_sponsorship_overrides_strong_lca_history():
    # The Cyient case: 35 LCAs/year, but JD explicitly denies.
    v = _call(
        jd_status="no_sponsorship",
        jd_confidence=0.95,
        jd_evidence="We are unable to sponsor work visas for this position.",
        lca_count_12mo=35,
    )
    assert v.status == "no_sponsorship"
    assert v.confidence == 0.95
    assert "explicit denial" in v.reasoning.lower()


def test_us_citizen_only_overrides_lca_history():
    v = _call(
        jd_status="us_citizen_only",
        jd_confidence=0.98,
        jd_evidence="U.S. citizenship required due to ITAR.",
        lca_count_12mo=200,  # even a heavy filer
    )
    assert v.status == "us_citizen_only"


# ---- Rule 2: strong LCA history alone decides "sponsors" ----


def test_strong_lca_history_wins_when_jd_silent():
    v = _call(jd_status="unclear", jd_confidence=0.05, lca_count_12mo=50)
    assert v.status == "sponsors"
    assert v.confidence >= 0.90


def test_threshold_boundary_is_five():
    # 4 LCAs is NOT strong; 5 IS strong.
    v_below = _call(jd_status="unclear", jd_confidence=0.05, lca_count_12mo=4)
    v_at = _call(jd_status="unclear", jd_confidence=0.05, lca_count_12mo=5)
    # Below threshold falls into Rule 6 ("mild positive"), still 'sponsors'
    # but with lower confidence.
    assert v_below.status == "sponsors"
    assert v_at.status == "sponsors"
    assert v_at.confidence >= v_below.confidence


# ---- Rule 3: JD says sponsors + LCA history confirms ----


def test_jd_sponsors_with_lca_history_confirmed():
    v = _call(
        jd_status="sponsors",
        jd_confidence=0.8,
        jd_evidence="We sponsor H-1B visas.",
        lca_count_12mo=3,
    )
    assert v.status == "sponsors"
    assert v.confidence >= 0.85


# ---- Rule 4: JD claims sponsors but ZERO LCAs in 12mo → downgrade to unclear ----


def test_jd_sponsors_but_zero_lcas_downgrades():
    v = _call(
        jd_status="sponsors",
        jd_confidence=0.90,
        jd_evidence="We sponsor visas.",
        lca_count_12mo=0,  # specifically zero, not None
    )
    assert v.status == "unclear"
    assert v.confidence < 0.5


# ---- Rule 5: JD claims sponsors, company NOT in LCA db (unknown) → trust with discount ----


def test_jd_sponsors_unknown_company_trusts_with_discount():
    v = _call(
        jd_status="sponsors",
        jd_confidence=0.9,
        jd_evidence="We sponsor visas.",
        lca_count_12mo=None,  # unknown company
    )
    assert v.status == "sponsors"
    # discount applied
    assert v.confidence < 0.9
    assert v.confidence > 0


# ---- Rule 6: JD silent + mild LCA history (1-4 in 12mo) ----


def test_jd_silent_mild_history_mild_positive():
    v = _call(jd_status="unclear", jd_confidence=0.05, lca_count_12mo=2)
    assert v.status == "sponsors"
    # Not "strong" confidence
    assert 0.4 < v.confidence < 0.85


# ---- Default: JD silent + no LCA data → unclear ----


def test_default_unclear():
    v = _call(jd_status="unclear", jd_confidence=0.05, lca_count_12mo=None)
    assert v.status == "unclear"


# ---- Unknown JD status normalizes to 'unclear' ----


def test_unknown_jd_status_normalizes():
    v = _call(jd_status="totally_made_up_status", jd_confidence=0.9, lca_count_12mo=None)
    assert v.status == "unclear"
    assert v.confidence <= 0.1


# ---- CPT/OPT flag passes through ----


def test_cpt_opt_flag_preserved():
    v = _call(
        jd_status="sponsors",
        jd_confidence=0.95,
        lca_count_12mo=10,
        cpt_opt=True,
    )
    assert v.cpt_opt_friendly is True


# ---- parse_classifier_output tolerance ----


class TestParseClassifierOutput:
    """The LLM is asked for raw JSON but sometimes emits code fences or extra
    prose. The parser has to be tolerant."""

    def test_plain_json(self):
        out = parse_classifier_output('{"status": "sponsors", "confidence": 0.9}')
        assert out["status"] == "sponsors"

    def test_fenced_json(self):
        out = parse_classifier_output('```json\n{"status": "sponsors"}\n```')
        assert out["status"] == "sponsors"

    def test_fenced_unlabeled(self):
        out = parse_classifier_output('```\n{"status": "unclear"}\n```')
        assert out["status"] == "unclear"

    def test_extra_prose_wrapping_json(self):
        out = parse_classifier_output(
            'Here is the verdict:\n{"status": "no_sponsorship", "confidence": 0.97}\nDone.'
        )
        assert out["status"] == "no_sponsorship"

    def test_invalid_json_raises(self):
        import json
        with pytest.raises(json.JSONDecodeError):
            parse_classifier_output("not even close to json")
