"""Master Agent CLI — paste a natural-language request, get a response.

Smoke-test fixtures live in tests/master_agent_fixtures.py. Run all fixtures
with --fixtures.

Run from backend/:
    venv/bin/python -m scripts.run_master_agent "Find me ML jobs in Seattle"
    venv/bin/python -m scripts.run_master_agent --fixtures
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from agents import run_master_agent

FIXTURES = [
    {
        "name": "search_ml_seattle",
        "input": "Find me machine learning jobs in Seattle",
        "expect_intent": "search_jobs",
    },
    {
        "name": "search_sponsors_only",
        "input": "Show me the top 5 sponsor-friendly software engineering jobs",
        "expect_intent": "search_jobs",
    },
    {
        "name": "search_by_company",
        "input": "What Anthropic positions do we have?",
        "expect_intent": "search_jobs",
    },
    {
        "name": "ambiguous",
        "input": "Snowflake",
        "expect_intent": "clarify",
    },
    {
        "name": "customize_resume",
        "input": (
            "Customize my resume for this JD:\n\n"
            "At Anthropic, we're hiring a Senior Software Engineer for our "
            "Inference Runtime team. You will work on optimizing the runtime "
            "that serves Claude. Required: 5+ years of distributed systems "
            "experience, strong Python and C++ skills, experience with GPU "
            "computing. We sponsor work visas including H-1B for qualified "
            "candidates."
        ),
        "expect_intent": "customize_resume",
    },
    {
        "name": "sponsorship_only",
        "input": (
            "Does this job sponsor visas? Position: Software Engineer at "
            "Lockheed Martin. Must be authorized to work in the United States "
            "without sponsorship now or in the future. We are unable to "
            "sponsor work visas for this position."
        ),
        "expect_intent": "classify_sponsorship_for_jd",
    },
]


async def run_one(user_message: str, verbose: bool) -> None:
    result = await run_master_agent(user_message)
    print(f"\n>>> USER: {user_message[:120]}{'…' if len(user_message) > 120 else ''}\n")
    print(f"intent:     {result.intent}")
    if result.classifier_reasoning:
        print(f"reasoning:  {result.classifier_reasoning}")
    if result.tool_args:
        print(f"tool_args:  {result.tool_args}")
    if result.error:
        print(f"error:      {result.error}")
    if verbose and result.tool_result is not None:
        import json
        print("--- raw tool_result (first 800 chars) ---")
        s = json.dumps(result.tool_result, default=str, ensure_ascii=False, indent=2)
        print(s[:800])
        if len(s) > 800:
            print("…")
    print("--- response ---")
    print(result.response)
    print()


async def run_fixtures(verbose: bool) -> int:
    passes = 0
    fails: list[tuple[str, str, str]] = []
    for fx in FIXTURES:
        print("=" * 80)
        print(f"FIXTURE: {fx['name']}   (expect intent: {fx['expect_intent']})")
        print("=" * 80)
        result = await run_master_agent(fx["input"])
        intent_ok = result.intent == fx["expect_intent"]
        if intent_ok:
            passes += 1
        else:
            fails.append((fx["name"], fx["expect_intent"], result.intent))
        await run_one(fx["input"], verbose)
        print(f"intent match: {'✅ PASS' if intent_ok else '❌ FAIL'}")

    print("=" * 80)
    print(f"SUMMARY: {passes}/{len(FIXTURES)} intent matches.")
    if fails:
        print("FAILS:")
        for name, expected, got in fails:
            print(f"  {name}: expected={expected} got={got}")
    return 0 if not fails else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("user_message", nargs="?", help="Natural-language request")
    p.add_argument("--fixtures", action="store_true", help="Run the 6-case NL fixture suite")
    p.add_argument("--verbose", action="store_true", help="Print raw tool_result")
    ns = p.parse_args()

    if ns.fixtures:
        sys.exit(asyncio.run(run_fixtures(ns.verbose)))
    if not ns.user_message:
        p.error("provide a user_message or --fixtures")
    asyncio.run(run_one(ns.user_message, ns.verbose))
