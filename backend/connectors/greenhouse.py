"""Greenhouse public job-board connector.

Pattern: each company has its own public board at
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
No auth required. Returns all currently-open postings for that company.

Because Greenhouse is per-company (not search-API style like Adzuna), we
maintain a curated list of sponsor-friendly tech companies. Override via
constructor `boards=[...]` to scrape a different set.

Keyword / location filters are applied post-hoc against title and location.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, ClassVar

import httpx

from .base import JobConnector, NormalizedListing, register_connector

GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards"
DEFAULT_TIMEOUT = 30.0
DEFAULT_CONCURRENCY = 8  # parallel board fetches

# Curated starter list of tech companies that:
#  (a) use Greenhouse as their ATS, AND
#  (b) historically sponsor H-1B / open to international students.
#
# Slug == path segment in their boards URL, lowercase. Verify by visiting
#   https://boards.greenhouse.io/{slug}
# If a slug returns 404, the company moved to another ATS (often Lever or
# Workday) and should be removed.
DEFAULT_BOARDS: list[str] = [
    "stripe",
    "anthropic",
    "openai",
    "snowflakecomputing",   # Snowflake's actual slug
    "datadog",
    "doordash",
    "figma",
    "gitlab",
    "plaid",
    "robinhood",
    "mongodb",
    "hashicorp",
    "twilio",
    "atlassian",
    "scaleai",              # Scale AI
    "brex",
    "instacart",
    "postman",
    "sentry",
    "vercel",
    "mercury",
    "ramp",
    "airbnb",
    "rippling",
]


def _strip_html(text: str | None) -> str | None:
    if not text:
        return text
    # Greenhouse `content` is HTML-escaped HTML — unescape entities then drop tags.
    from html import unescape
    s = unescape(text)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def _parse_one(raw: dict[str, Any], company_fallback: str) -> NormalizedListing | None:
    source_id = raw.get("id")
    title = raw.get("title")
    if not (source_id and title):
        return None

    company = raw.get("company_name") or company_fallback

    loc_obj = raw.get("location") or {}
    location = loc_obj.get("name") if isinstance(loc_obj, dict) else None

    updated = raw.get("updated_at")
    try:
        scraped_at = (
            datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if updated
            else datetime.utcnow()
        )
    except (TypeError, ValueError):
        scraped_at = datetime.utcnow()

    return NormalizedListing(
        source="greenhouse",
        source_id=str(source_id),
        source_url=raw.get("absolute_url"),
        company=company,
        title=title,
        location=location,
        description_raw=_strip_html(raw.get("content")),
        scraped_at=scraped_at,
    )


@register_connector
class GreenhouseConnector(JobConnector):
    source_name = "greenhouse"

    DEFAULT_BOARDS: ClassVar[list[str]] = DEFAULT_BOARDS

    def __init__(self, boards: list[str] | None = None):
        self.boards = boards or list(DEFAULT_BOARDS)

    async def _fetch_one_board(
        self, client: httpx.AsyncClient, slug: str
    ) -> list[NormalizedListing]:
        url = f"{GREENHOUSE_BASE}/{slug}/jobs"
        params = {"content": "true"}
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 404:
                # Slug moved off Greenhouse; skip quietly so the rest of the
                # batch still completes. Caller can prune the list later.
                return []
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
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

        # Post-hoc filters.
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

        # Most-recent first.
        flat.sort(key=lambda x: x.scraped_at, reverse=True)
        return flat[:max_results]
