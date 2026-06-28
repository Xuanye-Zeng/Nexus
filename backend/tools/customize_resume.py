"""customize_resume tool — wraps the M1 customize pipeline.

Reuses the same chain as POST /api/customize-resume: jd_keyword_extractor +
RAG section selection + bullet_rewriter, plus a sponsorship classification
pass against the SAME JD so the agent response can surface both signals.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import SessionLocal
from models import PromptTemplate, ResumeProfile, ResumeSection, User
from services.embedding import embed_text  # noqa: F401  (kept for future RAG batch use)
from services.llm import get_llm
from services.retrieval import top_k_sections_for_jd
from services.sponsorship import parse_classifier_output, resolve_sponsorship

from .registry import register_tool

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
RAG_FILTERED_TYPES = {"project", "experience"}
ALWAYS_KEEP_TYPES = {"skill", "education"}


async def _active_prompt(s: AsyncSession, name: str) -> PromptTemplate:
    row = (
        await s.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name, PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(f"no active prompt template {name!r}")
    return row


async def _resolve_profile(s: AsyncSession) -> ResumeProfile:
    user = (
        await s.execute(select(User).where(User.email == ALEX_EMAIL))
    ).scalar_one()
    profile = (
        await s.execute(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == user.id)
            .order_by(ResumeProfile.version.desc())
            .limit(1)
        )
    ).scalar_one()
    return profile


def _render_section(sec: ResumeSection) -> str:
    c = sec.content_json
    if sec.section_type == "project":
        return f"### {c['title']} ({c['dates']})\n" + "\n".join(
            f"- {b}" for b in c["bullets"]
        )
    if sec.section_type == "experience":
        return f"### {c['role']}, {c['company']} ({c['dates']})\n" + "\n".join(
            f"- {b}" for b in c["bullets"]
        )
    if sec.section_type == "education":
        details = "\n".join(f"- {d}" for d in c.get("details", []))
        head = f"### {c['degree']}, {c['school']} ({c['dates']})"
        return f"{head}\n{details}" if details else head
    if sec.section_type == "skill":
        return f"- {c['category']}: {', '.join(c['items'])}"
    return ""


def _render_resume(sections: list[ResumeSection]) -> str:
    by_type: dict[str, list[ResumeSection]] = {}
    for sec in sections:
        by_type.setdefault(sec.section_type, []).append(sec)
    blocks: list[str] = []
    if "project" in by_type:
        blocks.append("## PROJECTS\n\n" + "\n\n".join(_render_section(x) for x in by_type["project"]))
    if "experience" in by_type:
        blocks.append("## EXPERIENCE\n\n" + "\n\n".join(_render_section(x) for x in by_type["experience"]))
    if "education" in by_type:
        blocks.append("## EDUCATION\n\n" + "\n\n".join(_render_section(x) for x in by_type["education"]))
    if "skill" in by_type:
        blocks.append("## SKILLS\n" + "\n".join(_render_section(x) for x in by_type["skill"]))
    return "\n\n".join(blocks)


@register_tool("customize_resume")
async def customize_resume(args: dict[str, Any]) -> dict[str, Any]:
    """Customize resume against a pasted JD.

    Args:
      jd_text (str, required): full JD text.
      top_k (int | None): if set, narrow project+experience to top-K by RAG.

    Returns: {jd_extraction, rewritten_resume, sponsorship, sections_used,
              prompt_versions}.
    """
    jd_text = (args.get("jd_text") or "").strip()
    if not jd_text:
        return {"error": "customize_resume requires a non-empty jd_text argument."}

    top_k = args.get("top_k")
    if top_k is not None:
        top_k = int(top_k)

    async with SessionLocal() as s:
        extractor_prompt = await _active_prompt(s, "jd_keyword_extractor")
        rewriter_prompt = await _active_prompt(s, "bullet_rewriter")
        sponsor_prompt = await _active_prompt(s, "sponsorship_classifier")
        profile = await _resolve_profile(s)

        all_sections = (
            await s.execute(
                select(ResumeSection).where(ResumeSection.profile_id == profile.id)
            )
        ).scalars().all()

        if top_k is None:
            selected = all_sections
            audit_layer = "all"
        else:
            ranked = await top_k_sections_for_jd(s, jd_text, profile.id, k=100)
            filtered = [r for r in ranked if r.section.section_type in RAG_FILTERED_TYPES][:top_k]
            always_keep = [
                sec for sec in all_sections if sec.section_type in ALWAYS_KEEP_TYPES
            ]
            selected = [r.section for r in filtered] + always_keep
            audit_layer = f"rag_top_{top_k}"

    resume_md = _render_resume(selected)
    extractor_llm = get_llm("jd_keyword_extractor")
    rewriter_llm = get_llm("bullet_rewriter")
    sponsorship_llm = get_llm("sponsorship_classifier")

    extraction = extractor_llm.invoke(
        [
            SystemMessage(content=extractor_prompt.content),
            HumanMessage(content=f"## JD\n{jd_text}"),
        ]
    ).content
    rewrite = rewriter_llm.invoke(
        [
            SystemMessage(content=rewriter_prompt.content),
            HumanMessage(content=f"## JD\n{jd_text}\n\n## RESUME SECTIONS\n{resume_md}"),
        ]
    ).content

    # Sponsorship pass — same prompt the M2 pipeline uses.
    sponsor_raw = sponsorship_llm.invoke(
        [
            SystemMessage(content=sponsor_prompt.content),
            HumanMessage(content=f"## JD\n{jd_text}"),
        ]
    ).content
    try:
        sponsor_out = parse_classifier_output(sponsor_raw)
    except Exception:
        sponsor_out = {"status": "unclear", "evidence": "", "cpt_opt_signal": False, "confidence": 0.0}

    verdict = resolve_sponsorship(
        jd_status=sponsor_out.get("status", "unclear"),
        jd_confidence=float(sponsor_out.get("confidence", 0.0)),
        jd_evidence=sponsor_out.get("evidence", "") or "",
        cpt_opt_signal=bool(sponsor_out.get("cpt_opt_signal", False)),
        lca_count_12mo=None,  # no company name here — JD-only verdict
        lca_most_recent_year=None,
    )

    return {
        "jd_extraction": extraction,
        "rewritten_resume": rewrite,
        "sponsorship": {
            "status": verdict.status,
            "confidence": verdict.confidence,
            "evidence": verdict.evidence,
            "cpt_opt_friendly": verdict.cpt_opt_friendly,
            "reasoning": verdict.reasoning,
        },
        "sections_used_count": len(selected),
        "rag_mode": audit_layer,
        "prompt_versions": {
            "jd_keyword_extractor": extractor_prompt.version,
            "bullet_rewriter": rewriter_prompt.version,
            "sponsorship_classifier": sponsor_prompt.version,
        },
    }
