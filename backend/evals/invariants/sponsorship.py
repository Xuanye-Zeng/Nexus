"""Invariants for `sponsorship_classifier` LLM output.

The classifier is asked to return strict JSON with 4 keys:
    { status, evidence, cpt_opt_signal, confidence }

These invariants encode what MUST be true regardless of the specific JD:
  1. The output parses as JSON (via the same tolerance the pipeline uses).
  2. `status` is one of the 4 declared enum values.
  3. `confidence` is a float in [0, 1].
  4. `cpt_opt_signal` is a boolean.
  5. `evidence` is EITHER empty OR a verbatim substring of the JD
     (whitespace-normalized). Fabricated quotes are the classifier's most
     dangerous failure mode — we cite this string in the UI as proof.
  6. Confidence is GROUNDED: a verdict with no evidence, or an `unclear`
     verdict, cannot also claim high confidence. Range alone (invariant 3) is
     not enough — {status: "unclear", evidence: "", confidence: 0.95} passes
     every other check while telling the UI to trust a number the model had
     nothing to base on.
"""
from __future__ import annotations

import re

from services.sponsorship import JD_STATUSES, parse_classifier_output

from ..base import InvariantResult


def _normalize_ws(s: str) -> str:
    """Collapse all whitespace runs to single space. Preserves punctuation +
    case (evidence should be verbatim except for whitespace)."""
    return re.sub(r"\s+", " ", s).strip()


def check_json_parses(raw_output: str, jd_text: str) -> InvariantResult:
    try:
        parse_classifier_output(raw_output)
        return InvariantResult(name="json_parses", passed=True)
    except Exception as e:  # noqa: BLE001 — surface why parse failed
        return InvariantResult(
            name="json_parses", passed=False, detail=f"{type(e).__name__}: {e}"
        )


def check_status_enum(raw_output: str, jd_text: str) -> InvariantResult:
    try:
        parsed = parse_classifier_output(raw_output)
    except Exception:
        return InvariantResult(
            name="status_enum", passed=False, detail="upstream JSON parse failed"
        )
    status = parsed.get("status", "")
    if status in JD_STATUSES:
        return InvariantResult(name="status_enum", passed=True)
    return InvariantResult(
        name="status_enum",
        passed=False,
        detail=f"status={status!r} not in {sorted(JD_STATUSES)}",
    )


def check_confidence_range(raw_output: str, jd_text: str) -> InvariantResult:
    try:
        parsed = parse_classifier_output(raw_output)
    except Exception:
        return InvariantResult(
            name="confidence_range", passed=False, detail="upstream JSON parse failed"
        )
    conf = parsed.get("confidence")
    if not isinstance(conf, (int, float)):
        return InvariantResult(
            name="confidence_range",
            passed=False,
            detail=f"confidence={conf!r} is not a number",
        )
    if 0.0 <= float(conf) <= 1.0:
        return InvariantResult(name="confidence_range", passed=True)
    return InvariantResult(
        name="confidence_range", passed=False, detail=f"confidence={conf} not in [0,1]"
    )


def check_cpt_opt_bool(raw_output: str, jd_text: str) -> InvariantResult:
    try:
        parsed = parse_classifier_output(raw_output)
    except Exception:
        return InvariantResult(
            name="cpt_opt_bool", passed=False, detail="upstream JSON parse failed"
        )
    val = parsed.get("cpt_opt_signal")
    if isinstance(val, bool):
        return InvariantResult(name="cpt_opt_bool", passed=True)
    return InvariantResult(
        name="cpt_opt_bool",
        passed=False,
        detail=f"cpt_opt_signal={val!r} is not a bool",
    )


def check_evidence_verbatim(raw_output: str, jd_text: str) -> InvariantResult:
    """Evidence must be either empty (unclear cases) or a verbatim substring
    of the JD after whitespace normalization. Fabricated evidence would
    poison the UI's "here's why we said sponsors" trust chain."""
    try:
        parsed = parse_classifier_output(raw_output)
    except Exception:
        return InvariantResult(
            name="evidence_verbatim",
            passed=False,
            detail="upstream JSON parse failed",
        )
    evidence = parsed.get("evidence", "") or ""
    if not evidence.strip():
        return InvariantResult(name="evidence_verbatim", passed=True)

    if _normalize_ws(evidence) in _normalize_ws(jd_text):
        return InvariantResult(name="evidence_verbatim", passed=True)

    # Provide a short excerpt of what didn't match for debugging.
    excerpt = evidence[:80] + ("…" if len(evidence) > 80 else "")
    return InvariantResult(
        name="evidence_verbatim",
        passed=False,
        detail=f"evidence not in JD: {excerpt!r}",
    )


# A verdict the model cannot point at evidence for is, at best, a guess. We sort
# and filter listings by this number in the UI, so an ungrounded 0.95 is worse
# than a low score: it ranks a guess above a cited match.
UNGROUNDED_CONFIDENCE_CEILING = 0.5


def check_confidence_grounded(raw_output: str, jd_text: str) -> InvariantResult:
    """High confidence requires something to be confident about.

    Complements check_confidence_range: that one only bounds the number to
    [0, 1]. This one ties it to the rest of the verdict — empty evidence or an
    `unclear` status caps how confident the classifier is allowed to sound.
    Mirrors the clamp services/sponsorship.py already applies to unparseable
    statuses.
    """
    try:
        parsed = parse_classifier_output(raw_output)
    except Exception:
        return InvariantResult(
            name="confidence_grounded", passed=False, detail="upstream JSON parse failed"
        )

    conf = parsed.get("confidence")
    if not isinstance(conf, (int, float)):
        return InvariantResult(
            name="confidence_grounded", passed=False, detail="upstream confidence not numeric"
        )
    conf = float(conf)

    has_evidence = bool((parsed.get("evidence") or "").strip())
    status = parsed.get("status", "")
    ungrounded = (not has_evidence) or status == "unclear"

    if ungrounded and conf > UNGROUNDED_CONFIDENCE_CEILING:
        reason = "no evidence cited" if not has_evidence else "status is 'unclear'"
        return InvariantResult(
            name="confidence_grounded",
            passed=False,
            detail=f"confidence={conf} exceeds {UNGROUNDED_CONFIDENCE_CEILING} but {reason}",
        )
    return InvariantResult(name="confidence_grounded", passed=True)


ALL_INVARIANTS = [
    check_json_parses,
    check_status_enum,
    check_confidence_range,
    check_cpt_opt_bool,
    check_evidence_verbatim,
    check_confidence_grounded,
]
