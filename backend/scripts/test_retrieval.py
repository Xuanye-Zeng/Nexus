"""Quick RAG verification: embed JD + rank all of Alex's resume sections.

Prints a ranked list with section_type, cosine distance, and a 70-char preview
of each section's content. No LLM call — pure pgvector + nomic-embed-text.

Run from backend/:  venv/bin/python -m scripts.test_retrieval
"""
import asyncio
from pathlib import Path

from sqlalchemy import select

from db import SessionLocal
from models import ResumeProfile, User
from services.retrieval import top_k_sections_for_jd

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
JD_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "jd_amazon_sde.md"


def _preview(content: dict, section_type: str, max_chars: int = 70) -> str:
    if section_type == "project":
        text = content.get("title", "")
    elif section_type == "experience":
        text = f"{content.get('role', '')} @ {content.get('company', '')}"
    elif section_type == "education":
        text = f"{content.get('degree', '')} @ {content.get('school', '')}"
    elif section_type == "skill":
        items = content.get("items", [])
        text = f"{content.get('category', '')}: {', '.join(items[:5])}"
    else:
        text = str(content)[:max_chars]
    return text[:max_chars]


async def main() -> None:
    jd = JD_FIXTURE.read_text()
    print(f"JD: {len(jd)} chars from {JD_FIXTURE.name}")

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
        print(f"Profile: v{profile.version} '{profile.label}' (id={profile.id})\n")

        ranked = await top_k_sections_for_jd(s, jd, profile.id, k=20)

    print(f"{'rank':>4}  {'distance':>8}  {'type':<11}  preview")
    print("-" * 100)
    for i, r in enumerate(ranked, 1):
        print(
            f"{i:>4}  {r.distance:>8.4f}  {r.section.section_type:<11}  "
            f"{_preview(r.section.content_json, r.section.section_type)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
