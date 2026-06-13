"""Adzuna Jobs API connector.

Docs: https://developer.adzuna.com/docs/search
Endpoint: GET /v1/api/jobs/{country}/search/{page}
Free tier: 1000 calls / month.

Search-API style: takes keyword + location, returns matching listings
from across all employers. Each Adzuna result has a stable upstream id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config import settings

from .base import JobConnector, NormalizedListing, register_connector

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_TIMEOUT = 30.0
PAGE_SIZE = 50  # Adzuna max


def _credentials_ready() -> None:
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY.get_secret_value():
        raise RuntimeError(
            "Adzuna credentials missing. Set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
        )


def _parse_one(raw: dict[str, Any]) -> NormalizedListing | None:
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
        scraped_at = (
            datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created_str
            else datetime.utcnow()
        )
    except (TypeError, ValueError):
        scraped_at = datetime.utcnow()

    return NormalizedListing(
        source="adzuna",
        source_id=str(source_id),
        source_url=raw.get("redirect_url"),
        company=company,
        title=title,
        location=location,
        description_raw=raw.get("description"),
        scraped_at=scraped_at,
    )


@register_connector
class AdzunaConnector(JobConnector):
    source_name = "adzuna"

    async def fetch(
        self,
        keyword: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[NormalizedListing]:
        _credentials_ready()

        country = settings.ADZUNA_COUNTRY.lower()
        per_page = min(max_results, PAGE_SIZE)
        pages_needed = max(1, (max_results + per_page - 1) // per_page)

        params: dict[str, Any] = {
            "app_id": settings.ADZUNA_APP_ID,
            "app_key": settings.ADZUNA_APP_KEY.get_secret_value(),
            "results_per_page": per_page,
            "what": keyword or "software engineer",
            "content-type": "application/json",
        }
        if location:
            params["where"] = location

        listings: list[NormalizedListing] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for page in range(1, pages_needed + 1):
                url = f"{ADZUNA_BASE}/{country}/search/{page}"
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if not results:
                    break
                listings.extend(p for p in (_parse_one(r) for r in results) if p)
                if len(listings) >= max_results:
                    break

        return listings[:max_results]
