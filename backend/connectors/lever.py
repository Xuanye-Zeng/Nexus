"""Lever public job-board connector.

Pattern: each company has its own public board at
    https://api.lever.co/v0/postings/{slug}?mode=json
No auth required. Returns all currently-open postings.

Same per-company pattern as Greenhouse — we maintain a curated list of
sponsor-friendly tech companies that use Lever. Override via constructor
`boards=[...]`.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from .base import JobConnector, NormalizedListing, register_connector

LEVER_BASE = "https://api.lever.co/v0/postings"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONCURRENCY = 8

# Curated starter list — verify by visiting https://jobs.lever.co/{slug}.
# Remove slugs that 404 (company migrated to a different ATS).
DEFAULT_BOARDS: list[str] = [
    "matchgroup",
    "discord",
    "anduril",
    "ramp",            # also on Greenhouse historically; both may work
    "applied-intuition",
    "scaleai",
    "perplexity-ai",
    "character",       # character.ai
    "runway",
    "huggingface",
    "groq",
    "together-ai",
    "modal-labs",
    "fly-io",
    "supabase",
    "vercel",
    "linear",
    "notion",
    "retool",
    "loom",
    "checkr",
    "cruise",
    "ramp",
    "weave",
    "patreon",
]


def _parse_one(raw: dict[str, Any], company_fallback: str) -> NormalizedListing | None:
    source_id = raw.get("id")
    title = raw.get("text")
    if not (source_id and title):
        return None

    cats = raw.get("categories") or {}
    location = cats.get("location") if isinstance(cats, dict) else None

    # Lever sometimes provides the company name on the posting, sometimes not.
    # Fall back to the board slug formatted as title-case.
    company = raw.get("companyName") or company_fallback.replace("-", " ").title()

    updated_ms = raw.get("updatedAt") or raw.get("createdAt")
    try:
        scraped_at = (
            datetime.fromtimestamp(int(updated_ms) / 1000, tz=UTC)
            if updated_ms
            else datetime.utcnow()
        )
    except (TypeError, ValueError):
        scraped_at = datetime.utcnow()

    description = raw.get("descriptionPlain") or raw.get("description")
    # `description` is HTML — Lever provides a plain-text twin we prefer.

    return NormalizedListing(
        source="lever",
        source_id=str(source_id),
        source_url=raw.get("hostedUrl"),
        company=company,
        title=title,
        location=location,
        description_raw=description,
        scraped_at=scraped_at,
    )


@register_connector
class LeverConnector(JobConnector):
    source_name = "lever"

    DEFAULT_BOARDS: ClassVar[list[str]] = DEFAULT_BOARDS

    def __init__(self, boards: list[str] | None = None):
        # Dedup while preserving order — DEFAULT_BOARDS above has "ramp" twice
        # for resilience to my own typos; do the same favor to overrides.
        seen: set[str] = set()
        self.boards = []
        for b in boards or DEFAULT_BOARDS:
            if b not in seen:
                seen.add(b)
                self.boards.append(b)

    async def _fetch_one_board(
        self, client: httpx.AsyncClient, slug: str
    ) -> list[NormalizedListing]:
        url = f"{LEVER_BASE}/{slug}"
        params = {"mode": "json"}
        try:
            resp = await client.get(url, params=params)
            if resp.status_code in (404, 410):
                return []
            resp.raise_for_status()
            jobs = resp.json()
            if not isinstance(jobs, list):
                return []
        except (httpx.HTTPError, ValueError):
            return []
        return [p for p in (_parse_one(j, slug) for j in jobs) if p]

    async def fetch(
        self,
        keyword: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[NormalizedListing]:
        sem = asyncio.Semaphore(DEFAULT_CONCURRENCY)

        async def _bounded(client, slug):
            async with sem:
                return await self._fetch_one_board(client, slug)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            all_lists = await asyncio.gather(
                *(_bounded(client, slug) for slug in self.boards)
            )

        flat = [item for sublist in all_lists for item in sublist]

        if keyword:
            kw_lower = keyword.lower()
            flat = [
                lst for lst in flat
                if kw_lower in lst.title.lower()
                or (lst.description_raw and kw_lower in lst.description_raw.lower())
            ]
        if location:
            loc_lower = location.lower()
            flat = [
                lst for lst in flat
                if lst.location and loc_lower in lst.location.lower()
            ]

        flat.sort(key=lambda x: x.scraped_at, reverse=True)
        return flat[:max_results]
