"""Benchmark local Ollama LLMs for sponsorship_classifier.

Runs each candidate model over the 5 canonical sponsorship fixtures and
reports: per-call latency, total time, JSON parse success rate, and label
accuracy vs the expected labels (same expected map as
run_sponsorship_classifier.py).

This is the hard data needed to decide:
  - Stay on Groq llama-3.3-70b (4.4s, but 100K TPD daily ceiling)
  - Switch to local Ollama (slower per-call, but no rate limit)
  - Or hybrid (Groq for premium bullet_rewriter, local for bulk classify)

Run from backend/:
    venv/bin/python -m scripts.benchmark_local_classifier
    venv/bin/python -m scripts.benchmark_local_classifier --models qwen2.5:14b qwen2.5:3b
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from sqlalchemy import select

from config import settings
from db import SessionLocal
from models import PromptTemplate

DEFAULT_MODELS = ["qwen2.5:14b", "qwen2.5:3b"]

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sponsorship_cases"
PROMPT_NAME = "sponsorship_classifier"

EXPECTED_MAP = {
    "explicit_denial": ("no_sponsorship", False),
    "explicit_sponsors": ("sponsors", True),
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
    return re.match(r"case_\d+_(.+)\.md", filename).group(1)


def _parse_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        m = re.search(r"\{[^{}]*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    return json.loads(s)


async def bench_one_model(model: str, prompt: str, fixtures: list[Path]) -> dict:
    print(f"\n=== {model} ===")
    print(f"{'fixture':<35}  {'expected':<20}  {'got':<18}  {'cpt':<3}  {'time':>5}s  result")
    print("-" * 110)

    llm = ChatOllama(
        model=model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )

    results = []
    times = []
    parse_failures = 0
    label_passes = 0

    for fx in fixtures:
        label = _parse_expected_label(fx.name)
        expected_status, expected_cpt = EXPECTED_MAP[label]
        jd_text = fx.read_text()

        t0 = time.perf_counter()
        try:
            resp = await llm.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=f"## JD\n{jd_text}")]
            )
            elapsed = time.perf_counter() - t0
            raw = resp.content
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"{fx.name:<35}  {expected_status:<20}  ERROR              -    {elapsed:>5.1f}s  {type(e).__name__}: {str(e)[:50]}")
            results.append({"fixture": fx.name, "error": str(e), "elapsed": elapsed})
            times.append(elapsed)
            continue

        times.append(elapsed)
        try:
            out = _parse_json(raw)
        except json.JSONDecodeError as e:
            parse_failures += 1
            print(f"{fx.name:<35}  {expected_status:<20}  PARSE-ERROR        -    {elapsed:>5.1f}s  {str(e)[:50]}")
            results.append({"fixture": fx.name, "parse_error": str(e), "raw": raw[:200], "elapsed": elapsed})
            continue

        status = out.get("status", "?")
        cpt = bool(out.get("cpt_opt_signal", False))
        ok = status == expected_status and cpt == expected_cpt
        if ok:
            label_passes += 1
        print(
            f"{fx.name:<35}  {expected_status:<20}  {status:<18}  "
            f"{'T' if cpt else 'F':<3}  {elapsed:>5.1f}s  {'PASS' if ok else 'FAIL'}"
        )
        results.append({
            "fixture": fx.name,
            "status": status,
            "cpt_opt_signal": cpt,
            "expected_status": expected_status,
            "expected_cpt": expected_cpt,
            "elapsed": elapsed,
            "pass": ok,
        })

    print("-" * 110)
    total = sum(times)
    avg = total / len(times) if times else 0
    print(
        f"summary: total={total:.1f}s  avg/call={avg:.1f}s  "
        f"label_pass={label_passes}/{len(fixtures)}  "
        f"parse_fail={parse_failures}/{len(fixtures)}"
    )
    return {
        "model": model,
        "total_seconds": total,
        "avg_seconds_per_call": avg,
        "label_pass_rate": label_passes / len(fixtures) if fixtures else 0,
        "parse_failures": parse_failures,
        "calls": len(fixtures),
        "per_fixture": results,
    }


async def main(models: list[str]) -> int:
    prompt = await fetch_prompt()
    fixtures = sorted(FIXTURES_DIR.glob("case_*.md"))
    print(f"prompt: {len(prompt)} chars; fixtures: {len(fixtures)}")
    print("baseline (Groq llama-3.3-70b): ~4.4s/call, 5/5 pass, but capped at 100K TPD\n")

    summaries = []
    for m in models:
        summaries.append(await bench_one_model(m, prompt, fixtures))

    print("\n\n" + "=" * 80)
    print("OVERALL SUMMARY")
    print("=" * 80)
    print(f"{'model':<25}  {'avg/call':>10}  {'total':>8}  {'pass':>6}  {'parse-fail':>10}")
    for s in summaries:
        print(
            f"{s['model']:<25}  {s['avg_seconds_per_call']:>8.1f}s  "
            f"{s['total_seconds']:>6.1f}s  "
            f"{int(s['label_pass_rate'] * s['calls'])}/{s['calls']:<3}  "
            f"{s['parse_failures']:>10}"
        )
    print("\nfor reference: Groq llama-3.3-70b avg 4.4s/call, 5/5 pass, 100K TPD ceiling")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ns = p.parse_args()
    sys.exit(asyncio.run(main(ns.models)))
