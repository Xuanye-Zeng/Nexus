"""Gate CI on the invariant eval harness.

These tests exercise `evals/` in cached mode — no LLM calls, no DB. They:

  1. Assert that the committed cached outputs pass all invariants (100%).
     If a prompt or invariant edit breaks something, CI catches it here.

  2. Adversarially prove each invariant fires on obviously-broken output
     — the invariants themselves are what we trust, so we need to trust
     they aren't silently vacuous.
"""
from __future__ import annotations

import pytest

from evals.invariants import bullet_rewriter as br_inv
from evals.invariants import sponsorship as sp_inv
from evals.runner import evaluate_bullet_rewriter_cached, evaluate_sponsorship_cached

# ---------- cached-output gate ----------


def test_sponsorship_cached_all_invariants_pass():
    report = evaluate_sponsorship_cached()
    assert report.n_checks > 0, "no sponsorship cache — bootstrap with --live"
    assert report.pass_rate == 1.0, "\n" + report.render()


def test_bullet_rewriter_cached_hard_invariants_pass():
    """CI-blocking gate on the correctness/safety invariants: structure,
    number preservation, skills categories. Failures here are regressions
    that MUST NOT ship (a fabricated metric or missing section)."""
    report = evaluate_bullet_rewriter_cached(invariant_set="hard")
    assert report.n_checks > 0, "no bullet_rewriter cache — bootstrap with --live"
    assert report.pass_rate == 1.0, "\n" + report.render()


def test_bullet_rewriter_cached_soft_invariants_tracked():
    """SOFT invariants (fillers, length) track stochastic style slippage.
    llama-3.3-70b at temperature 0 has been observed emitting `utilizing`
    despite the explicit ban — the eval harness surfaces this without
    blocking every commit on a prompt-vs-model race. Threshold is a floor
    that catches catastrophic regressions (e.g. every bullet suddenly has
    an em-dash) while tolerating the known-known ~1-per-10-bullet slip."""
    report = evaluate_bullet_rewriter_cached(invariant_set="soft")
    assert report.n_checks > 0, "no bullet_rewriter cache"
    # Floor at 40% — well above chance, well below strict. If the model
    # starts systematically emitting fillers on every bullet, this trips.
    assert report.pass_rate >= 0.4, (
        f"soft invariant pass rate collapsed to {report.pass_rate:.0%}\n"
        + report.render()
    )


# ---------- sponsorship invariants: adversarial ----------

_GOOD_JD = "We sponsor H-1B visas for qualified candidates."


def test_sponsorship_json_parses_catches_garbage():
    r = sp_inv.check_json_parses("this is not json at all!", _GOOD_JD)
    assert not r.passed


def test_sponsorship_status_enum_catches_typo():
    bad = '{"status": "sponsorz", "evidence": "", "cpt_opt_signal": false, "confidence": 0.5}'
    r = sp_inv.check_status_enum(bad, _GOOD_JD)
    assert not r.passed
    assert "sponsorz" in r.detail


def test_sponsorship_confidence_catches_out_of_range():
    bad = '{"status": "sponsors", "evidence": "", "cpt_opt_signal": false, "confidence": 1.7}'
    r = sp_inv.check_confidence_range(bad, _GOOD_JD)
    assert not r.passed


def test_sponsorship_cpt_opt_bool_catches_string():
    bad = '{"status": "sponsors", "evidence": "", "cpt_opt_signal": "yes", "confidence": 0.5}'
    r = sp_inv.check_cpt_opt_bool(bad, _GOOD_JD)
    assert not r.passed


def test_sponsorship_evidence_verbatim_catches_fabricated_quote():
    # Evidence text is NOT in the JD.
    bad = (
        '{"status": "sponsors", "evidence": "We offer premium H-1B fast-track sponsorship", '
        '"cpt_opt_signal": false, "confidence": 0.9}'
    )
    r = sp_inv.check_evidence_verbatim(bad, _GOOD_JD)
    assert not r.passed


def test_sponsorship_evidence_verbatim_ignores_whitespace_diff():
    """Whitespace differences alone shouldn't fail — resume/JD text often has
    trailing spaces or line-wrap artifacts."""
    jd = "We sponsor H-1B visas   for qualified candidates."
    good = (
        '{"status": "sponsors", "evidence": "We sponsor H-1B visas for qualified candidates.", '
        '"cpt_opt_signal": false, "confidence": 0.9}'
    )
    r = sp_inv.check_evidence_verbatim(good, jd)
    assert r.passed


def test_sponsorship_evidence_empty_is_ok():
    """`unclear` cases legitimately return empty evidence."""
    good = (
        '{"status": "unclear", "evidence": "", "cpt_opt_signal": false, "confidence": 0.05}'
    )
    r = sp_inv.check_evidence_verbatim(good, _GOOD_JD)
    assert r.passed


# ---------- bullet_rewriter invariants: adversarial ----------


def test_br_structure_catches_missing_section():
    bad = "## PROJECTS\n- BEFORE: foo\nAFTER: foo\nREASON: bar\n"  # no EXPERIENCE, no SKILLS
    r = br_inv.check_structure(bad)
    assert not r.passed
    assert "missing headers" in r.detail


def test_br_number_preservation_catches_fabricated_percent():
    bad = (
        "## PROJECTS\n"
        "- BEFORE: Built a caching layer that improved read speed.\n"
        "AFTER: Built a caching layer that improved read speed by 40%.\n"
        "REASON: targets stuff\n\n"
        "## EXPERIENCE\n"
        "- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_number_preservation(bad)
    assert not r.passed
    assert "40%" in r.detail


def test_br_number_preservation_catches_dropped_metric():
    bad = (
        "## PROJECTS\n"
        "- BEFORE: Cut latency by 30% using ElastiCache.\n"
        "AFTER: Cut latency using ElastiCache.\n"
        "REASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_number_preservation(bad)
    assert not r.passed
    assert "30%" in r.detail


def test_br_number_preservation_accepts_keep():
    """AFTER: KEEP is a legal signal, not a rewrite — invariant skips."""
    good = (
        "## PROJECTS\n"
        "- BEFORE: Cut latency by 30% using ElastiCache.\n"
        "AFTER: KEEP\n"
        "REASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_number_preservation(good)
    assert r.passed


@pytest.mark.parametrize(
    "filler",
    ["leverage", "leveraging", "utilize", "utilizing", "synergy"],
)
def test_br_no_forbidden_fillers_catches_each(filler: str):
    bad = (
        "## PROJECTS\n"
        f"- BEFORE: Built a system.\nAFTER: Built a system to {filler} scale.\nREASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_no_forbidden_fillers(bad)
    assert not r.passed
    assert filler in r.detail


def test_br_no_forbidden_fillers_catches_em_dash():
    bad = (
        "## PROJECTS\n"
        "- BEFORE: Built a system.\nAFTER: Built a system — clean.\nREASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_no_forbidden_fillers(bad)
    assert not r.passed
    assert "em-dash" in r.detail


def test_br_skills_categories_catches_reorder():
    bad = (
        "## PROJECTS\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        # Programming Languages missing, Cloud is first
        "- Cloud & Infrastructure: AWS\n- Backend & Data: SQL\n- ML & AI: PyTorch\n"
        "- Core: DSA\n- Programming Languages: Python\n"
    )
    r = br_inv.check_skills_categories(bad)
    assert not r.passed


def test_br_extract_bullets_handles_multiple_projects():
    md = (
        "## PROJECTS\n"
        "### ML Pipeline (2025)\n"
        "- BEFORE: Foo\nAFTER: Bar\nREASON: baz\n\n"
        "- BEFORE: Second\nAFTER: Third\nREASON: fourth\n\n"
        "### CloudScale (2024)\n"
        "- BEFORE: Fifth\nAFTER: Sixth\nREASON: seventh\n"
    )
    bullets = br_inv.extract_bullets(md)
    assert len(bullets) == 3
    assert bullets[0].before == "Foo"
    assert bullets[0].after == "Bar"
    assert bullets[2].before == "Fifth"


def test_br_length_bounded_catches_runaway():
    bad = (
        "## PROJECTS\n"
        "- BEFORE: Short bullet.\n"
        f"AFTER: {'very long text ' * 20}\n"
        "REASON: y\n\n"
        "## EXPERIENCE\n- BEFORE: x\nAFTER: x\nREASON: y\n\n"
        "## SKILLS\n"
        "- Programming Languages: Python\n- Cloud & Infrastructure: AWS\n"
        "- Backend & Data: SQL\n- ML & AI: PyTorch\n- Core: DSA\n"
    )
    r = br_inv.check_length_bounded(bad)
    assert not r.passed
