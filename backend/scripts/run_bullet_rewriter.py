"""End-to-end test: pull the active bullet_rewriter prompt + a JD fixture +
Alex's resume sections from DB, render, call Groq, print LLM output.

Optionally narrows project + experience sections by pgvector RAG ranking
against the JD embedding (skills + education are always kept — they are
structurally required for the rewriter's SKILLS output section).

Run from backend/:
    venv/bin/python -m scripts.run_bullet_rewriter              # all sections
    venv/bin/python -m scripts.run_bullet_rewriter --top-k 3    # top-3 RAG-ranked project+experience + all skills/edu
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from sqlalchemy import select

from config import settings
from db import SessionLocal
from models import PromptTemplate, ResumeProfile, ResumeSection, User
from services.retrieval import top_k_sections_for_jd

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
JD_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "jd_amazon_sde.md"
PROMPT_NAME = "bullet_rewriter"

RAG_FILTERED_TYPES = {"project", "experience"}  # RAG ranks these
ALWAYS_KEEP_TYPES = {"skill", "education"}       # rewriter needs these every time


async def fetch_prompt(s) -> str:
    row = (
        await s.execute(
            select(PromptTemplate)
            .where(
                PromptTemplate.name == PROMPT_NAME,
                PromptTemplate.is_active.is_(True),
            )
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
    ).scalar_one()
    return row.content


async def resolve_profile(s) -> ResumeProfile:
    user = (await s.execute(select(User).where(User.email == ALEX_EMAIL))).scalar_one()
    return (
        await s.execute(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == user.id)
            .order_by(ResumeProfile.version.desc())
            .limit(1)
        )
    ).scalar_one()


async def fetch_all_sections(s, profile_id) -> list[ResumeSection]:
    return (
        await s.execute(
            select(ResumeSection).where(ResumeSection.profile_id == profile_id)
        )
    ).scalars().all()


async def select_sections(
    s, jd_text: str, profile: ResumeProfile, top_k: int | None
) -> tuple[list[ResumeSection], list[tuple[ResumeSection, float | None]]]:
    """Return (sections_to_send, audit_rows).

    audit_rows: list of (section, distance) ordered as sent. distance is
    None for ALWAYS_KEEP_TYPES (no RAG score) or when top_k is None.
    """
    all_sections = await fetch_all_sections(s, profile.id)

    if top_k is None:
        return all_sections, [(sec, None) for sec in all_sections]

    # RAG over project + experience only
    ranked = await top_k_sections_for_jd(s, jd_text, profile.id, k=100)
    filtered_ranked = [
        r for r in ranked if r.section.section_type in RAG_FILTERED_TYPES
    ][:top_k]
    kept_ids = {r.section.id for r in filtered_ranked}

    always_keep = [
        sec for sec in all_sections if sec.section_type in ALWAYS_KEEP_TYPES
    ]

    selected = [r.section for r in filtered_ranked] + always_keep
    audit = [(r.section, r.distance) for r in filtered_ranked] + [
        (sec, None) for sec in always_keep
    ]
    return selected, audit


def _render_one(section: ResumeSection) -> str:
    c: dict[str, Any] = section.content_json
    if section.section_type == "project":
        bullets = "\n".join(f"- {b}" for b in c["bullets"])
        return f"### {c['title']} ({c['dates']})\n{bullets}"
    if section.section_type == "experience":
        bullets = "\n".join(f"- {b}" for b in c["bullets"])
        return f"### {c['role']}, {c['company']} ({c['dates']})\n{bullets}"
    if section.section_type == "education":
        details = "\n".join(f"- {d}" for d in c.get("details", []))
        head = f"### {c['degree']}, {c['school']} ({c['dates']})"
        return f"{head}\n{details}" if details else head
    if section.section_type == "skill":
        return f"- {c['category']}: {', '.join(c['items'])}"
    return ""


def render_sections(sections: list[ResumeSection]) -> str:
    by_type: dict[str, list[ResumeSection]] = {}
    for sec in sections:
        by_type.setdefault(sec.section_type, []).append(sec)

    blocks: list[str] = []
    if "project" in by_type:
        blocks.append(
            "## PROJECTS\n\n" + "\n\n".join(_render_one(x) for x in by_type["project"])
        )
    if "experience" in by_type:
        blocks.append(
            "## EXPERIENCE\n\n" + "\n\n".join(_render_one(x) for x in by_type["experience"])
        )
    if "education" in by_type:
        blocks.append(
            "## EDUCATION\n\n" + "\n\n".join(_render_one(x) for x in by_type["education"])
        )
    if "skill" in by_type:
        blocks.append("## SKILLS\n" + "\n".join(_render_one(x) for x in by_type["skill"]))
    return "\n\n".join(blocks)


def _section_label(sec: ResumeSection) -> str:
    c = sec.content_json
    if sec.section_type == "project":
        return c.get("title", "?")
    if sec.section_type == "experience":
        return f"{c.get('role', '?')} @ {c.get('company', '?')}"
    if sec.section_type == "education":
        return f"{c.get('degree', '?')} @ {c.get('school', '?')}"
    if sec.section_type == "skill":
        return c.get("category", "?")
    return "?"


async def main(top_k: int | None) -> None:
    jd = JD_FIXTURE.read_text()
    async with SessionLocal() as s:
        prompt = await fetch_prompt(s)
        profile = await resolve_profile(s)
        sections, audit = await select_sections(s, jd, profile, top_k)

    sections_text = render_sections(sections)
    user_msg = f"## JD\n{jd}\n\n## RESUME SECTIONS\n{sections_text}"

    mode = "ALL sections" if top_k is None else f"RAG top-{top_k} (project+experience) + all skills/education"
    print("=" * 70, file=sys.stderr)
    print(f"mode:          {mode}", file=sys.stderr)
    print(f"prompt:        {len(prompt)} chars", file=sys.stderr)
    print(f"jd:            {len(jd)} chars", file=sys.stderr)
    print(f"sections:      {len(sections)} rows -> {len(sections_text)} chars", file=sys.stderr)
    print(f"user message:  {len(user_msg)} chars", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print(f"{'sent':>4}  {'distance':>10}  {'type':<11}  preview", file=sys.stderr)
    for i, (sec, dist) in enumerate(audit, 1):
        d = f"{dist:.4f}" if dist is not None else "keep"
        print(f"{i:>4}  {d:>10}  {sec.section_type:<11}  {_section_label(sec)[:55]}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    print(f"calling Groq model={settings.GROQ_MODEL} ...", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY.get_secret_value(),
    )
    resp = llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=user_msg),
        ]
    )

    print("=" * 70, file=sys.stderr)
    print("LLM OUTPUT:", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(resp.content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="If set, narrow project + experience to top-K by pgvector cosine "
             "distance to JD. Skills + education are always kept.",
    )
    ns = parser.parse_args()
    asyncio.run(main(ns.top_k))
