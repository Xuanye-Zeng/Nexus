"""Benchmark email_classifier against the 8 fixture cases. Prints per-case
result + summary; exit code != 0 if any case mis-classifies.

Filename convention: case_NN_<expected_category>.md

Run from backend/:  venv/bin/python -m scripts.run_email_classifier
"""
import asyncio
import re
import sys
from pathlib import Path

from db import SessionLocal
from services.email_classifier import classify_email

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "email_cases"


def _parse_expected(filename: str) -> str:
    m = re.match(r"case_\d+_(.+)\.md", filename)
    if not m:
        raise ValueError(f"unrecognized fixture name: {filename}")
    return m.group(1)


def _parse_email(text: str) -> dict:
    """Extract From / Subject / Received / Body sections."""
    fields: dict[str, str] = {}
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
            # any other header marks the start of the body
            in_body = True
        elif in_body:
            body_lines.append(line)
        else:
            # plain line before the body header — usually blank lines after headers
            if line.strip() and not (sender and subject and received):
                # weak heuristic; just treat as body start
                in_body = True
                body_lines.append(line)
    return {
        "sender": sender,
        "subject": subject,
        "received_at": received,
        "body": "\n".join(body_lines).strip(),
    }


async def main() -> int:
    fixtures = sorted(FIXTURES_DIR.glob("case_*.md"))
    if not fixtures:
        print(f"no fixtures in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    print(
        f"{'case':<40}  {'expected':<25}  {'got':<25}  {'imp':>3}  {'conf':>5}  pass"
    )
    print("-" * 130)

    passed = 0
    fails = []
    async with SessionLocal() as s:
        for fx in fixtures:
            expected = _parse_expected(fx.name)
            parsed = _parse_email(fx.read_text())
            cls = await classify_email(s, **parsed)
            ok = cls.category == expected
            if ok:
                passed += 1
            else:
                fails.append((fx.name, expected, cls.category))
            print(
                f"{fx.name:<40}  {expected:<25}  {cls.category:<25}  "
                f"{cls.importance_score:>3}  {cls.confidence:>5.2f}  "
                f"{'PASS' if ok else 'FAIL'}"
            )

    print("-" * 130)
    print(f"{passed}/{len(fixtures)} categories correct.")
    if fails:
        print("FAILS:")
        for name, exp, got in fails:
            print(f"  {name}: expected={exp} got={got}")
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
