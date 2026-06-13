"""Adzuna Jobs API connector — fetches normalized job listings.

Docs: https://developer.adzuna.com/docs/search
Endpoint: GET /v1/api/jobs/{country}/search/{page}
Free tier: 1000 calls / month — plenty for personal use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from config import settings

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_RESULTS_PER_PAGE = 50  # max allowed by Adzuna
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass
class AdzunaListing:
    """Normalized shape independent of the upstream JSON layout."""
    source: str  # always "adzuna"
    source_id: str
    source_url: str | None
    company: str
    title: str
    location: str | None
    description_raw: str | None
    scraped_at: datetime

    def __repr__(self) -> str:
        return (
            f"AdzunaListing(id={self.source_id!r}, company={self.company!r}, "
            f"title={self.title!r}, loc={self.location!r})"
        )


def _credentials_set() -> None:
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY.get_secret_value():
        raise RuntimeError(
            "Adzuna credentials missing. Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
        )


def _parse_one(raw: dict[str, Any]) -> AdzunaListing | None:
    """Convert one Adzuna result item into AdzunaListing. Returns None if required fields missing."""
    source_id = raw.get("id")
    title = raw.get("title")
    company_obj = raw.get("company") or {}
    company = company_obj.get("display_name") if isinstance(company_obj, dict) else None
    if not (source_id and title and company):
        return None

    location_obj = raw.get("location") or {}
    location = (
        location_obj.get("display_name") if isinstance(location_obj, dict) else None
    )

    created_str = raw.get("created")
    try:
        # Adzuna emits ISO-8601 with Z; strip Z and parse
        scraped_at = (
            datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created_str
            else datetime.utcnow()
        )
    except (TypeError, ValueError):
        scraped_at = datetime.utcnow()

    return AdzunaListing(
        source="adzuna",
        source_id=str(source_id),
        source_url=raw.get("redirect_url"),
        company=company,
        title=title,
        location=location,
        description_raw=raw.get("description"),
        scraped_at=scraped_at,
    )


async def fetch_listings(
    keyword: str,
    location: str | None = None,
    page: int = 1,
    results_per_page: int = DEFAULT_RESULTS_PER_PAGE,
    country: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[AdzunaListing]:
    """Fetch one page of Adzuna search results.

    Args:
        keyword: free-text query (e.g. "software engineer", "machine learning")
        location: city, state, or country (e.g. "Seattle", "New York")
        page: 1-indexed page number
        results_per_page: 1-50 (Adzuna caps at 50)
        country: ISO country code; defaults to settings.ADZUNA_COUNTRY (us)
        client: pass an existing httpx.AsyncClient for connection reuse;
                if None, a fresh client is created and closed for this call.

    Returns:
        list[AdzunaListing] — possibly empty if no matches or all rows malformed.
    """
    _credentials_set()
    country = (country or settings.ADZUNA_COUNTRY).lower()

    url = f"{ADZUNA_BASE}/{country}/search/{page}"
    params: dict[str, Any] = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_APP_KEY.get_secret_value(),
        "results_per_page": min(max(results_per_page, 1), 50),
        "what": keyword,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)

    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    results = data.get("results", [])
    parsed = [p for p in (_parse_one(r) for r in results) if p is not None]
    return parsed
