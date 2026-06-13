"""get_top_resume_sections_for_jd tool — RAG-only debug peek.

For the user who wants to know "which parts of my resume are the strongest
match for this JD?" without going through the full customize_resume chain
(no LLM rewrite, just retrieval). Useful for tuning the resume itself.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from db import SessionLocal
from models import ResumeProfile, User
from services.retrieval import top_k_sections_for_jd

from .registry import register_tool

ALEX_EMAIL = "zeng.xuan@northeastern.edu"


def _section_label(content: dict, section_type: str) -> str:
    if section_type == "project":
        return content.get("title", "?")
    if section_type == "experience":
        return f"{content.get('role', '?')} @ {content.get('company', '?')}"
    if section_type == "education":
        return f"{content.get('degree', '?')} @ {content.get('school', '?')}"
    if section_type == "skill":
        return content.get("category", "?")
    return "?"


@register_tool("get_top_resume_sections_for_jd")
async def get_top_resume_sections_for_jd(args: dict[str, Any]) -> dict[str, Any]:
    """RAG-only retrieval against the user's active resume.

    Args:
      jd_text (str, required): JD text.
      k (int, optional, default 8): how many sections to return.

    Returns: {profile_version, sections: [{rank, distance, section_type, label}]}.
    """
    jd_text = (args.get("jd_text") or "").strip()
    if not jd_text:
        return {"error": "get_top_resume_sections_for_jd requires non-empty jd_text"}
    k = int(args.get("k", 8))

    async with SessionLocal() as s:
        user = (await s.execute(select(User).where(User.email == ALEX_EMAIL))).scalar_one()
        profile = (
            await s.execute(
                select(ResumeProfile)
                .where(ResumeProfile.user_id == user.id)
                .order_by(ResumeProfile.version.desc())
                .limit(1)
            )
        ).scalar_one()
        ranked = await top_k_sections_for_jd(s, jd_text, profile.id, k=k)

    return {
        "profile_version": profile.version,
        "sections": [
            {
                "rank": i,
                "distance": r.distance,
                "section_type": r.section.section_type,
                "label": _section_label(r.section.content_json, r.section.section_type),
            }
            for i, r in enumerate(ranked, 1)
        ],
    }
