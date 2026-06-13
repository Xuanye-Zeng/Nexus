"""Run the active jd_keyword_extractor prompt against a JD fixture and print
the structured extraction. Used for prompt-quality verification and as the
upstream step for the resume_customizer pipeline.

Run from backend/:  venv/bin/python -m scripts.run_jd_keyword_extractor
                    venv/bin/python -m scripts.run_jd_keyword_extractor --jd path/to/jd.md
"""
import argparse
import asyncio
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from db import SessionLocal
from models import PromptTemplate
from services.llm import describe_profile, get_llm

DEFAULT_JD = Path(__file__).resolve().parent.parent / "fixtures" / "jd_amazon_sde.md"
PROMPT_NAME = "jd_keyword_extractor"


async def fetch_prompt() -> str:
    async with SessionLocal() as s:
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


async def main(jd_path: Path) -> None:
    jd = jd_path.read_text()
    prompt = await fetch_prompt()

    print("=" * 70, file=sys.stderr)
    print(f"prompt: {len(prompt)} chars", file=sys.stderr)
    print(f"jd:     {len(jd)} chars from {jd_path.name}", file=sys.stderr)
    print(f"jd_keyword_extractor LLM: {describe_profile('jd_keyword_extractor')} ...", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    llm = get_llm("jd_keyword_extractor")
    resp = llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=f"## JD\n{jd}"),
        ]
    )

    print("=" * 70, file=sys.stderr)
    print("EXTRACTION:", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(resp.content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jd",
        type=Path,
        default=DEFAULT_JD,
        help="Path to JD markdown file (default: fixtures/jd_amazon_sde.md)",
    )
    ns = parser.parse_args()
    asyncio.run(main(ns.jd))
