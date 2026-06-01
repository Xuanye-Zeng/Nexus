"""End-to-end test: pull the active bullet_rewriter prompt + a JD fixture +
Alex's resume sections from DB, render, call Ollama, print LLM output.

Run from backend/:  venv/bin/python -m scripts.run_bullet_rewriter
"""
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

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
JD_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "jd_amazon_sde.md"
PROMPT_NAME = "bullet_rewriter"


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


async def fetch_sections(s) -> list[ResumeSection]:
    user = (await s.execute(select(User).where(User.email == ALEX_EMAIL))).scalar_one()
    profile = (
        await s.execute(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == user.id)
            .order_by(ResumeProfile.version.desc())
            .limit(1)
        )
    ).scalar_one()
    sections = (
        await s.execute(
            select(ResumeSection).where(ResumeSection.profile_id == profile.id)
        )
    ).scalars().all()
    return sections


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
        blocks.append("## PROJECTS\n\n" + "\n\n".join(_render_one(x) for x in by_type["project"]))
    if "experience" in by_type:
        blocks.append("## EXPERIENCE\n\n" + "\n\n".join(_render_one(x) for x in by_type["experience"]))
    if "education" in by_type:
        blocks.append("## EDUCATION\n\n" + "\n\n".join(_render_one(x) for x in by_type["education"]))
    if "skill" in by_type:
        blocks.append("## SKILLS\n" + "\n".join(_render_one(x) for x in by_type["skill"]))
    return "\n\n".join(blocks)


async def main() -> None:
    jd = JD_FIXTURE.read_text()
    async with SessionLocal() as s:
        prompt = await fetch_prompt(s)
        sections = await fetch_sections(s)

    sections_text = render_sections(sections)
    user_msg = f"## JD\n{jd}\n\n## RESUME SECTIONS\n{sections_text}"

    print("=" * 70, file=sys.stderr)
    print(f"prompt:        {len(prompt)} chars", file=sys.stderr)
    print(f"jd:            {len(jd)} chars", file=sys.stderr)
    print(f"sections:      {len(sections)} rows -> {len(sections_text)} chars", file=sys.stderr)
    print(f"user message:  {len(user_msg)} chars", file=sys.stderr)
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
    asyncio.run(main())
