"""CLI thin wrapper over `services.ingest_pipeline.ingest_from_source`.

The orchestration logic lives in the service module so the Master Agent
tool (`tools/ingest_jobs.py`) and the Celery task (`tasks.ingest_source`)
hit the same code path.

Run from backend/:
    venv/bin/python -m scripts.ingest_jobs --source adzuna --keyword "software engineer" --location Seattle
    venv/bin/python -m scripts.ingest_jobs --source greenhouse --keyword intern --max 30
    venv/bin/python -m scripts.ingest_jobs --source workday --max 25
    venv/bin/python -m scripts.ingest_jobs --source all --keyword engineer --max 15
    venv/bin/python -m scripts.ingest_jobs --source adzuna --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from connectors import list_connectors
from services.ingest_pipeline import EnrichedListing, ingest_from_source
from services.llm import describe_profile


def _print_progress(i: int, total: int, e: EnrichedListing) -> None:
    """Status line per listing — matches the original CLI output shape so
    nothing about the human-side ergonomics changed when the logic moved
    behind the service boundary."""
    v = e.verdict
    company = (e.row["company"] or "")[:25]
    match_score = e.row["match_score"]
    score_str = f"{match_score:.2f}" if match_score is not None else "-"
    lca = str(v.h1b_lca_count_recent) if v.h1b_lca_count_recent is not None else "-"
    print(
        f"  {i:>3}/{total:<3}  {company:<25}  {v.status:<16}  "
        f"{v.confidence:<5.2f}  {lca:>5}  {e.match_layer:<13}  "
        f"{score_str:<5}  {v.reasoning[:55]}"
    )


async def main(
    source: str,
    keyword: str | None,
    location: str | None,
    max_results: int,
    dry_run: bool,
) -> int:
    if source not in list_connectors():
        print(
            f"ERROR: unknown source {source!r}. Registered: {list_connectors()}",
            file=sys.stderr,
        )
        return 2

    print(f"sponsorship_classifier LLM: {describe_profile('sponsorship_classifier')}")
    print(
        f"Fetching via {source} connector "
        f"(keyword={keyword!r} location={location!r} max={max_results})..."
    )

    # The pipeline calls progress() once per enriched listing so we can
    # stream a status table without buffering.
    print(
        f"\n  {'#':>3}/{ 'tot':<3}  {'company':<25}  {'status':<16}  "
        f"{'conf':<5}  {'12mo':>5}  {'match':<13}  {'score':<5}  reasoning"
    )
    print("  " + "-" * 130)

    stats = await ingest_from_source(
        source=source,
        keyword=keyword,
        location=location,
        max_results=max_results,
        dry_run=dry_run,
        progress=_print_progress,
    )

    print(
        f"\nfetched={stats.fetched}  status={stats.by_status}  layers={stats.by_match_layer}"
    )
    if dry_run:
        print("(dry-run: no DB writes)")
    else:
        print(f"UPSERTed {stats.committed} listings into job_listings.")

    return 0


async def _run_all_sources(
    keyword: str | None, location: str | None, max_results: int, dry_run: bool
) -> int:
    """Fan out an ingest across every registered connector, serially.
    Serial (not parallel) because the per-listing pipeline already hits Ollama
    + Groq + Postgres + pgvector — running 4 sources concurrently just
    contends on the LLMs and slows the whole thing down."""
    sources = list_connectors()
    print(f"Running ingest across {len(sources)} source(s): {', '.join(sources)}\n")
    worst = 0
    for src in sources:
        print(f"\n{'=' * 60}\n>>> SOURCE: {src}\n{'=' * 60}")
        rc = await main(src, keyword, location, max_results, dry_run)
        worst = max(worst, rc or 0)
    return worst


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        choices=[*list_connectors(), "all"],
        default="adzuna",
        help=f"Connector to use, or 'all' to fan out. Available: {', '.join(list_connectors())} | all",
    )
    p.add_argument("--keyword", default=None)
    p.add_argument("--location", default=None)
    p.add_argument(
        "--max", type=int, default=20,
        help="Max listings to ingest (per source when --source all)",
    )
    p.add_argument("--dry-run", action="store_true")
    ns = p.parse_args()
    if ns.source == "all":
        sys.exit(asyncio.run(_run_all_sources(ns.keyword, ns.location, ns.max, ns.dry_run)))
    else:
        sys.exit(asyncio.run(main(ns.source, ns.keyword, ns.location, ns.max, ns.dry_run)))
