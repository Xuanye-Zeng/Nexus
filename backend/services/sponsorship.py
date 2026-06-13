"""Combine JD-text sponsorship signal with LCA filing history into a final verdict.

Implements plan §6 resolution logic:
  - Explicit JD denial (no_sponsorship / us_citizen_only) overrides everything,
    including a strong LCA history — an employer that says "no" in the posting
    will not sponsor for THIS role, regardless of past history.
  - Strong recent LCA history (>=5 in 12mo) makes 'sponsors' the answer even
    when JD is silent.
  - JD claim of 'sponsors' is downgraded when contradicted by zero LCA history.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


# JD-text-side status enum from the classifier.
JD_STATUSES = {"sponsors", "no_sponsorship", "us_citizen_only", "unclear"}

# Threshold for "strong" LCA history (rolling 12 months).
STRONG_LCA_THRESHOLD = 5


@dataclass(frozen=True)
class SponsorshipVerdict:
    status: str          # 'sponsors' | 'no_sponsorship' | 'us_citizen_only' | 'unclear'
    confidence: float    # 0.0 - 1.0
    evidence: str        # JD quote that drove the JD-side signal (verbatim)
    cpt_opt_friendly: bool
    h1b_lca_count_recent: int | None
    h1b_lca_year: int | None
    reasoning: str       # short human-readable explanation of which rule fired


def parse_classifier_output(raw: str) -> dict:
    """Best-effort parse of the sponsorship_classifier LLM output.

    The prompt asks for raw JSON. Tolerate fenced code blocks and trailing
    junk that some models emit despite the instruction.
    """
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # Some models emit a JSON object inside extra prose — extract via braces.
    if not s.startswith("{"):
        m = re.search(r"\{[^{}]*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    return json.loads(s)


def resolve_sponsorship(
    jd_status: str,
    jd_confidence: float,
    jd_evidence: str,
    cpt_opt_signal: bool,
    lca_count_12mo: int | None,
    lca_most_recent_year: int | None,
) -> SponsorshipVerdict:
    """Apply the plan §6 resolution logic. See module docstring."""
    if jd_status not in JD_STATUSES:
        jd_status = "unclear"
        jd_confidence = min(jd_confidence, 0.1)

    has_history = lca_count_12mo is not None and lca_count_12mo >= 1
    strong_history = (
        lca_count_12mo is not None and lca_count_12mo >= STRONG_LCA_THRESHOLD
    )

    # Rule 1: explicit JD denial overrides LCA history.
    if jd_status in ("no_sponsorship", "us_citizen_only"):
        return SponsorshipVerdict(
            status=jd_status,
            confidence=jd_confidence,
            evidence=jd_evidence,
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=lca_count_12mo,
            h1b_lca_year=lca_most_recent_year,
            reasoning="JD explicit denial overrides any LCA history",
        )

    # Rule 2: strong LCA history alone is decisive.
    if strong_history:
        return SponsorshipVerdict(
            status="sponsors",
            confidence=max(0.90, jd_confidence),
            evidence=jd_evidence or f"{lca_count_12mo} certified LCAs in last 12 months",
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=lca_count_12mo,
            h1b_lca_year=lca_most_recent_year,
            reasoning=f"strong LCA history ({lca_count_12mo} in 12mo >= {STRONG_LCA_THRESHOLD})",
        )

    # Rule 3: JD says sponsors AND at least some LCA history → confirmed.
    if jd_status == "sponsors" and has_history:
        return SponsorshipVerdict(
            status="sponsors",
            confidence=max(0.85, jd_confidence),
            evidence=jd_evidence,
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=lca_count_12mo,
            h1b_lca_year=lca_most_recent_year,
            reasoning="JD claim corroborated by LCA history",
        )

    # Rule 4: JD says sponsors but LCA shows zero filings → downgrade.
    if (
        jd_status == "sponsors"
        and lca_count_12mo is not None
        and lca_count_12mo == 0
    ):
        return SponsorshipVerdict(
            status="unclear",
            confidence=0.40,
            evidence=jd_evidence,
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=lca_count_12mo,
            h1b_lca_year=lca_most_recent_year,
            reasoning="JD claims sponsorship but no LCAs in 12mo — possibly aspirational",
        )

    # Rule 5: JD says sponsors and company not in LCA db (unknown).
    if jd_status == "sponsors" and lca_count_12mo is None:
        return SponsorshipVerdict(
            status="sponsors",
            confidence=jd_confidence * 0.8,
            evidence=jd_evidence,
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=None,
            h1b_lca_year=None,
            reasoning="JD claims sponsorship; company not in LCA db (small/new employer?)",
        )

    # Rule 6: JD silent but mild LCA history → mild positive.
    if jd_status == "unclear" and has_history:
        return SponsorshipVerdict(
            status="sponsors",
            confidence=0.55,
            evidence=f"{lca_count_12mo} certified LCAs in last 12 months",
            cpt_opt_friendly=cpt_opt_signal,
            h1b_lca_count_recent=lca_count_12mo,
            h1b_lca_year=lca_most_recent_year,
            reasoning="JD silent but employer has LCA history",
        )

    # Default: stay unclear.
    return SponsorshipVerdict(
        status="unclear",
        confidence=jd_confidence,
        evidence=jd_evidence,
        cpt_opt_friendly=cpt_opt_signal,
        h1b_lca_count_recent=lca_count_12mo,
        h1b_lca_year=lca_most_recent_year,
        reasoning="JD silent and no useful LCA signal",
    )
