"""ingest_jobs tool — thin wrapper over services.ingest_pipeline.

The Master Agent can ask "pull more Greenhouse backend engineer jobs" and
this tool fans the request out to the same code path the CLI + Celery
task use. Returns a small JSON-safe summary for the agent's responder.
"""
from __future__ import annotations

from typing import Any

from connectors import list_connectors
from services.ingest_pipeline import ingest_from_source

from .registry import register_tool

DEFAULT_MAX = 15  # cap agent-triggered ingests to keep latency reasonable
HARD_MAX = 30     # absolute upper bound regardless of what the LLM asked for


@register_tool("ingest_jobs")
async def ingest_jobs(args: dict[str, Any]) -> dict[str, Any]:
    """Pull fresh listings from a connector + enrich + UPSERT.

    Args:
      source (str, required): one of {adzuna, greenhouse, lever, workday}.
      keyword (str, optional): query keyword.
      location (str, optional): location filter (only Adzuna honors natively).
      max (int, optional, default 15, capped at HARD_MAX): how many to pull.

    Returns: {source, fetched, committed, filters, status_breakdown, sample}.
    """
    source = (args.get("source") or "").strip().lower()
    if not source:
        return {"error": f"ingest_jobs requires `source`. Available: {list_connectors()}"}
    if source not in list_connectors():
        return {"error": f"unknown source {source!r}. Available: {list_connectors()}"}

    max_results = min(int(args.get("max", DEFAULT_MAX)), HARD_MAX)
    keyword = args.get("keyword")
    location = args.get("location")

    stats = await ingest_from_source(
        source=source,
        keyword=keyword,
        location=location,
        max_results=max_results,
    )

    return {
        "source": source,
        "fetched": stats.fetched,
        "committed": stats.committed,
        "filters": {
            k: v
            for k, v in {"keyword": keyword, "location": location, "max": max_results}.items()
            if v
        },
        "status_breakdown": stats.by_status,
        "sample": stats.sample,
    }
