"""CLI entry point for the eval harness.

Usage from `backend/`:

    # Fast, deterministic — run invariants against committed cached outputs.
    venv/bin/python -m evals.run sponsorship
    venv/bin/python -m evals.run bullet_rewriter
    venv/bin/python -m evals.run all

    # Live — call the LLM for every fixture, overwrite the cache, then check.
    venv/bin/python -m evals.run sponsorship --live
    venv/bin/python -m evals.run bullet_rewriter --live   # (WIP — see below)

Exit codes:
    0 = all invariants pass
    1 = at least one invariant failed
    2 = fatal error (bad args, missing cache with --strict, LLM crash in --live)
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from .fixtures import load_sponsorship_fixtures
from .runner import (
    evaluate_bullet_rewriter_cached,
    evaluate_sponsorship_cached,
    save_cached,
)

_MODULES = ("sponsorship", "bullet_rewriter", "all")


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt_from_disk(name: str) -> tuple[str, int]:
    """Read the active prompt from `prompts/<name>.v*.md` without touching DB.

    Prompts are markdown with a YAML frontmatter block; we strip the frontmatter
    and return (body, version). Falls back to the highest-version file if
    multiple exist.
    """
    candidates = sorted(_PROMPTS_DIR.glob(f"{name}.v*.md"))
    if not candidates:
        raise FileNotFoundError(f"no prompt file found for {name}")
    path = candidates[-1]  # highest version
    text = path.read_text()
    # Strip frontmatter between the first two --- lines
    body = text
    version = 1
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4 :].lstrip("\n")
            m = re.search(r"^version:\s*(\d+)", fm, re.MULTILINE)
            if m:
                version = int(m.group(1))
    return body, version


async def _regenerate_sponsorship_cache() -> None:
    """Live mode for sponsorship_classifier: call the LLM against every fixture.

    Reads the prompt from disk (no DB required). LLM is loaded via
    `services.llm.get_llm` — for the sponsorship profile this is a local
    Ollama call, so the only external dependency is a running Ollama daemon.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from services.llm import get_llm

    prompt, prompt_version = _load_prompt_from_disk("sponsorship_classifier")

    llm = get_llm("sponsorship_classifier")
    model_label = getattr(llm, "model", "unknown")

    fixtures = load_sponsorship_fixtures()
    print(f"regenerating sponsorship cache: {len(fixtures)} fixtures", file=sys.stderr)
    for fx in fixtures:
        print(f"  → {fx.case_id} ...", end="", flush=True, file=sys.stderr)
        resp = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"## JD\n{fx.jd_text}"),
            ]
        )
        raw = resp.content
        save_cached(
            module="sponsorship",
            case_id=fx.case_id,
            output=raw,
            model=str(model_label),
            prompt_version=prompt_version,
            input_metadata={
                "expected_status": fx.expected_status,
                "expected_cpt_opt": fx.expected_cpt_opt,
            },
        )
        print(f" done ({len(raw)} chars)", file=sys.stderr)


async def _regenerate_bullet_rewriter_cache() -> None:
    """Live mode for bullet_rewriter — chains the same JD→sections→rewrite pipeline
    the /resume route uses. Requires: seeded resume sections in DB + active prompt.

    Currently drives one fixture (Amazon SDE JD). Adding fixtures = add markdown
    files to `backend/fixtures/` and register them in `fixtures.load_bullet_rewriter_fixtures`.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from sqlalchemy import select

    from db import SessionLocal
    from models import PromptTemplate, ResumeProfile, ResumeSection, User
    from services.llm import get_llm

    from .fixtures import load_bullet_rewriter_fixtures

    async with SessionLocal() as s:
        prompt_row = (
            await s.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == "bullet_rewriter",
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            )
        ).scalar_one()
        prompt = prompt_row.content
        prompt_version = prompt_row.version

        user = (
            await s.execute(select(User).limit(1))
        ).scalar_one()
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

    # Simple render — the /resume pipeline has a richer one; this is enough
    # to give the LLM all bullets.
    def _render(sec) -> str:
        c = sec.content_json
        if sec.section_type == "project":
            bullets = "\n".join(f"- {b}" for b in c["bullets"])
            return f"### {c['title']} ({c['dates']})\n{bullets}"
        if sec.section_type == "experience":
            bullets = "\n".join(f"- {b}" for b in c["bullets"])
            return f"### {c['role']}, {c['company']} ({c['dates']})\n{bullets}"
        if sec.section_type == "education":
            details = "\n".join(f"- {d}" for d in c.get("details", []))
            head = f"### {c['degree']}, {c['school']} ({c['dates']})"
            return f"{head}\n{details}" if details else head
        if sec.section_type == "skill":
            return f"- {c['category']}: {', '.join(c['items'])}"
        return ""

    blocks = {"project": [], "experience": [], "education": [], "skill": []}
    for sec in sections:
        blocks.setdefault(sec.section_type, []).append(_render(sec))

    parts = []
    if blocks["project"]:
        parts.append("## PROJECTS\n\n" + "\n\n".join(blocks["project"]))
    if blocks["experience"]:
        parts.append("## EXPERIENCE\n\n" + "\n\n".join(blocks["experience"]))
    if blocks["education"]:
        parts.append("## EDUCATION\n\n" + "\n\n".join(blocks["education"]))
    if blocks["skill"]:
        parts.append("## SKILLS\n" + "\n".join(blocks["skill"]))
    resume_md = "\n\n".join(parts)

    llm = get_llm("bullet_rewriter")
    model_label = getattr(llm, "model_name", getattr(llm, "model", "unknown"))

    fixtures = load_bullet_rewriter_fixtures()
    print(f"regenerating bullet_rewriter cache: {len(fixtures)} fixtures", file=sys.stderr)
    for fx in fixtures:
        print(f"  → {fx.case_id} ...", end="", flush=True, file=sys.stderr)
        resp = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"## JD\n{fx.jd_text}\n\n## RESUME SECTIONS\n{resume_md}"),
            ]
        )
        raw = resp.content
        save_cached(
            module="bullet_rewriter",
            case_id=fx.case_id,
            output=raw,
            model=str(model_label),
            prompt_version=prompt_version,
            input_metadata={"resume_profile_version": profile.version},
        )
        print(f" done ({len(raw)} chars)", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", choices=_MODULES)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call the LLM against every fixture + refresh the cache.",
    )
    args = parser.parse_args()

    exit_code = 0

    if args.live:
        # Live mode: refresh cache first, then run invariants against the fresh cache.
        if args.module in ("sponsorship", "all"):
            asyncio.run(_regenerate_sponsorship_cache())
        if args.module in ("bullet_rewriter", "all"):
            asyncio.run(_regenerate_bullet_rewriter_cache())

    if args.module in ("sponsorship", "all"):
        report = evaluate_sponsorship_cached()
        print(report.render())
        if report.pass_rate < 1.0:
            exit_code = 1

    if args.module in ("bullet_rewriter", "all"):
        report = evaluate_bullet_rewriter_cached()
        print(report.render())
        if report.pass_rate < 1.0:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
