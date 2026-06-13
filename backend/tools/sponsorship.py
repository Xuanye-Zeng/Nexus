"""classify_sponsorship_for_jd tool — ad-hoc JD-only sponsorship verdict.

For when the user pastes a JD and just wants the sponsorship signal, not a
resume rewrite. Skips the resume customizer entirely; runs only the
sponsorship_classifier prompt.

If the JD names a company that resolves in h1b_employers (rare for ad-hoc
pastes that may omit the legal name), we add the LCA history into the
final verdict via the same resolve_sponsorship() rules used by ingest.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from db import SessionLocal
from models import PromptTemplate
from services.employer_lookup import lookup_employer
from services.llm import get_llm
from services.sponsorship import parse_classifier_output, resolve_sponsorship

from .registry import register_tool


@register_tool("classify_sponsorship_for_jd")
async def classify_sponsorship_for_jd(args: dict[str, Any]) -> dict[str, Any]:
    """Classify visa sponsorship signal for a single JD.

    Args:
      jd_text (str, required): the JD body.
      company (str, optional): if provided, looked up in h1b_employers to
        layer LCA history onto the JD-text signal via the §6 resolver.

    Returns: {status, confidence, evidence, cpt_opt_friendly, reasoning,
              lca_count_12mo, lca_year}.
    """
    jd_text = (args.get("jd_text") or "").strip()
    company = (args.get("company") or "").strip() or None
    if not jd_text:
        return {"error": "classify_sponsorship_for_jd requires non-empty jd_text"}

    async with SessionLocal() as s:
        prompt_row = (
            await s.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == "sponsorship_classifier",
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            )
        ).scalar_one()

        emp_row = None
        match_layer = "miss"
        if company:
            emp_row, match_layer = await lookup_employer(s, company)

    llm = get_llm("sponsorship_classifier")
    resp = llm.invoke(
        [
            SystemMessage(content=prompt_row.content),
            HumanMessage(content=f"## JD\n{jd_text}"),
        ]
    )
    try:
        cls = parse_classifier_output(resp.content)
    except Exception:
        cls = {"status": "unclear", "evidence": "", "cpt_opt_signal": False, "confidence": 0.0}

    verdict = resolve_sponsorship(
        jd_status=cls.get("status", "unclear"),
        jd_confidence=float(cls.get("confidence", 0.0)),
        jd_evidence=cls.get("evidence", "") or "",
        cpt_opt_signal=bool(cls.get("cpt_opt_signal", False)),
        lca_count_12mo=emp_row.lca_count_last_12mo if emp_row else None,
        lca_most_recent_year=emp_row.most_recent_filing_year if emp_row else None,
    )

    return {
        "status": verdict.status,
        "confidence": verdict.confidence,
        "evidence": verdict.evidence,
        "cpt_opt_friendly": verdict.cpt_opt_friendly,
        "reasoning": verdict.reasoning,
        "lca_count_12mo": verdict.h1b_lca_count_recent,
        "lca_year": verdict.h1b_lca_year,
        "company_match_layer": match_layer if company else None,
    }
