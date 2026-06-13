"""Seed the 8 fixture emails into the emails table, running email_classifier
on each so the DB is populated for triage_emails / agent demos before OAuth
sync goes live.

Idempotent: upserts on (user_id, source='outlook', message_id='fixture-NN').

Run from backend/:  venv/bin/python -m scripts.seed_email_fixtures
"""
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db import SessionLocal
from models import Email, User
from services.email_classifier import classify_email

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "email_cases"
ALEX_EMAIL = "zeng.xuan@northeastern.edu"


def _parse_email_file(text: str) -> dict:
    sender = subject = received = None
    body_lines = []
    in_body = False
    for line in text.splitlines():
        if line.startswith("## From:"):
            sender = line[len("## From:"):].strip()
        elif line.startswith("## Subject:"):
            subject = line[len("## Subject:"):].strip()
        elif line.startswith("## Received:"):
            received = line[len("## Received:"):].strip()
        elif line.startswith("## "):
            in_body = True
        elif in_body:
            body_lines.append(line)
    return {
        "sender": sender,
        "subject": subject,
        "received_at": received,
        "body": "\n".join(body_lines).strip(),
    }


async def main() -> int:
    files = sorted(FIXTURES_DIR.glob("case_*.md"))
    if not files:
        print(f"no fixtures in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()
        print(f"seeding {len(files)} fixture emails for {ALEX_EMAIL}")

        for i, fx in enumerate(files, 1):
            parsed = _parse_email_file(fx.read_text())
            cls = await classify_email(s, **parsed)

            try:
                received_dt = (
                    datetime.fromisoformat(parsed["received_at"].replace("Z", "+00:00"))
                    if parsed["received_at"]
                    else None
                )
            except (TypeError, ValueError):
                received_dt = None

            sender_email = parsed["sender"] or ""
            # Split "addr@x (Display Name)" into addr + name if both present
            sender_name = None
            m = re.match(r"^([^()]+?)\s*\(([^)]+)\)\s*$", sender_email)
            if m:
                sender_email = m.group(1).strip()
                sender_name = m.group(2).strip()

            payload = {
                "user_id": user.id,
                "source": "outlook",       # placeholder until OAuth lands
                "message_id": f"fixture-{i:02d}",
                "subject": parsed["subject"],
                "sender": sender_email,
                "sender_name": sender_name,
                "body_preview": (parsed["body"] or "")[:200],
                "body_full": parsed["body"],
                "received_at": received_dt,
                "is_read": False,
                "is_deleted": False,
                "importance_score": cls.importance_score,
                "category": cls.category,
                "classifier_confidence": cls.confidence,
                "classifier_reasoning": cls.reasoning,
                "classifier_version": cls.prompt_version,
            }
            stmt = pg_insert(Email).values(payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "source", "message_id"],
                set_={
                    k: getattr(stmt.excluded, k)
                    for k in (
                        "subject", "sender", "sender_name",
                        "body_preview", "body_full", "received_at",
                        "importance_score", "category",
                        "classifier_confidence", "classifier_reasoning",
                        "classifier_version",
                    )
                },
            )
            await s.execute(stmt)
            print(
                f"  [{i}/{len(files)}] {fx.name:<40s}  "
                f"{cls.category:<25s}  imp={cls.importance_score}"
            )

        await s.commit()
    print(f"done.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
