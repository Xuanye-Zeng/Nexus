"""Run sponsorship_classifier against all fixtures in fixtures/sponsorship_cases/
and check classification accuracy against expected labels.

Expected labels are encoded in the filename: case_NN_<expected_status>.md
where expected_status is one of: explicit_denial / explicit_sponsors /
clearance_required / silent / intern_cpt.

The classifier's `status` field is mapped against expected as:
  explicit_denial      -> no_sponsorship
  explicit_sponsors    -> sponsors
  clearance_required   -> us_citizen_only
  silent               -> unclear
  intern_cpt           -> sponsors  (and cpt_opt_signal must be true)

Run from backend/:  venv/bin/python -m scripts.run_sponsorship_classifier
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from sqlalchemy import select

from config import settings
from db import SessionLocal
from models import PromptTemplate

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sponsorship_cases"
PROMPT_NAME = "sponsorship_classifier"

EXPECTED_MAP = {
    "explicit_denial": ("no_sponsorship", False),
    "explicit_sponsors": ("sponsors", True),     # JD also mentions F-1 OPT / STEM OPT
    "clearance_required": ("us_citizen_only", False),
    "silent": ("unclear", False),
    "intern_cpt": ("sponsors", True),
}


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


def _parse_expected_label(filename: str) -> str:
    m = re.match(r"case_\d+_(.+)\.md", filename)
    if not m:
        raise ValueError(f"unrecognized fixture name: {filename}")
    return m.group(1)


def _parse_classifier_output(text: str) -> dict:
    """The prompt asks for raw JSON — try to parse, tolerate fenced code blocks."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return json.loads(s)


async def main() -> int:
    prompt = await fetch_prompt()
    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY.get_secret_value(),
    )

    fixtures = sorted(FIXTURES_DIR.glob("case_*.md"))
    if not fixtures:
        print(f"no fixtures in {FIXTURES_DIR}", file=sys.stderr)
        return 1

    print(f"prompt: {len(prompt)} chars; running {len(fixtures)} cases on {settings.GROQ_MODEL}\n")
    print(f"{'case':<35}  {'expected':<20}  {'got_status':<18}  {'cpt':<3}  {'conf':<6}  {'pass'}")
    print("-" * 110)

    passed = 0
    for fx in fixtures:
        label = _parse_expected_label(fx.name)
        expected_status, expected_cpt = EXPECTED_MAP[label]

        jd_text = fx.read_text()
        resp = llm.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"## JD\n{jd_text}"),
            ]
        )

        try:
            out = _parse_classifier_output(resp.content)
        except json.JSONDecodeError as e:
            print(f"{fx.name:<35}  {expected_status:<20}  PARSE-ERROR        {e}")
            continue

        status_ok = out.get("status") == expected_status
        cpt_ok = bool(out.get("cpt_opt_signal", False)) == expected_cpt
        overall_pass = status_ok and cpt_ok
        if overall_pass:
            passed += 1

        print(
            f"{fx.name:<35}  {expected_status:<20}  {out.get('status', '?'):<18}  "
            f"{'T' if out.get('cpt_opt_signal') else 'F':<3}  "
            f"{out.get('confidence', 0):.2f}    "
            f"{'PASS' if overall_pass else 'FAIL'}"
        )
        if not overall_pass:
            print(f"  └─ evidence: {out.get('evidence', '')[:90]!r}")

    print("-" * 110)
    print(f"\n{passed}/{len(fixtures)} cases passed.")
    return 0 if passed == len(fixtures) else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
