"""Scan backend/prompts/*.md and upsert into prompt_templates.

Filename convention: <name>.v<version>.md  e.g. bullet_rewriter.v1.md
Frontmatter (YAML-ish):
    ---
    module: resume_customizer
    is_active: true
    ---
"""
import asyncio
import re
from pathlib import Path

from sqlalchemy import select

from db import SessionLocal
from models import PromptTemplate

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _parse_frontmatter(text: str) -> tuple[dict[str, str | bool], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    front_raw = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str | bool] = {}
    for line in front_raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v == "true":
            meta[k.strip()] = True
        elif v == "false":
            meta[k.strip()] = False
        else:
            meta[k.strip()] = v
    return meta, body


_FILENAME_RE = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>\d+)\.md$")


async def seed() -> None:
    files = sorted(PROMPTS_DIR.glob("*.md"))
    if not files:
        print(f"no prompt files found in {PROMPTS_DIR}")
        return

    async with SessionLocal() as s:
        for path in files:
            m = _FILENAME_RE.match(path.name)
            if not m:
                print(f"skip (bad filename): {path.name}")
                continue
            name = m.group("name")
            version = int(m.group("version"))
            meta, body = _parse_frontmatter(path.read_text())
            module = meta.get("module")
            is_active = meta.get("is_active", False)
            if not module:
                print(f"skip (no module in frontmatter): {path.name}")
                continue

            existing = (
                await s.execute(
                    select(PromptTemplate).where(
                        PromptTemplate.name == name,
                        PromptTemplate.version == version,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                s.add(
                    PromptTemplate(
                        name=name,
                        version=version,
                        module=module,
                        content=body.strip(),
                        is_active=bool(is_active),
                    )
                )
                action = "INSERT"
            else:
                existing.content = body.strip()
                existing.module = module
                existing.is_active = bool(is_active)
                action = "UPDATE"

            print(f"{action} {name} v{version} (module={module}, is_active={is_active})")

        await s.commit()


if __name__ == "__main__":
    asyncio.run(seed())
