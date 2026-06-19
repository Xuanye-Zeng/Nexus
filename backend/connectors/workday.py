"""Workday public job-board connector — Plan §4 M6.

Workday tenants expose a documented JSON Career-eXperience-Services (CXS)
endpoint at `/wday/cxs/{tenant}/{site}/jobs` that returns paginated job
listings. No login, no Playwright. The detail endpoint
`/wday/cxs/{tenant}/{site}/job/{external_path}` returns the full HTML
description.

Adding a tenant: append an entry to TENANTS with subdomain / cluster /
tenant_id / site_id. Visit the company's careers page; the URL pattern is
    https://{subdomain}.wd{N}.myworkdayjobs.com/{site_id}
and the cluster is `wd{N}`. The CXS path uses the same parts.

Falls back gracefully on 4xx/5xx so one bad tenant doesn't poison the batch.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import httpx

from .base import JobConnector, NormalizedListing, register_connector

DEFAULT_TIMEOUT = 30.0
DEFAULT_CONCURRENCY = 4  # per-tenant fan-out
PAGE_SIZE = 20            # CXS default; some tenants cap higher


@dataclass(frozen=True)
class WorkdayTenant:
    """One Workday-hosted careers site."""
    company_label: str   # what to store in JobListing.company
    subdomain: str       # the leftmost piece of the host
    cluster: str         # 'wd1' / 'wd5' / 'wd12' ...
    tenant: str          # path segment after /wday/cxs/  (usually == subdomain)
    site: str            # path segment after tenant

    @property
    def base_host(self) -> str:
        return f"https://{self.subdomain}.{self.cluster}.myworkdayjobs.com"

    @property
    def jobs_url(self) -> str:
        return f"{self.base_host}/wday/cxs/{self.tenant}/{self.site}/jobs"

    def detail_url(self, external_path: str) -> str:
        # externalPath looks like '/en-US/jobs-amazon/job/...'
        return f"{self.base_host}/wday/cxs/{self.tenant}/{self.site}{external_path}"

    def public_url(self, external_path: str) -> str:
        # Human-facing URL the listing renders at
        return f"{self.base_host}/{self.site}{external_path}"


# Curated starter list. Each entry was verified by `POST /wday/cxs/.../jobs`
# returning 200 with a non-zero `jobPostings` length. Tenants that 422 (most
# notably Amazon, JPMC, Capital One, Hilton, Visa, AT&T, Wells Fargo, Western
# Digital) reject the standard `{appliedFacets:{}, limit, offset, searchText}`
# body shape — they likely require a tenant-specific facet config that varies
# per Workday major version. Track in §10 M6 follow-ups; do NOT re-add to this
# list without a verified 200.
DEFAULT_TENANTS: list[WorkdayTenant] = [
    WorkdayTenant("NVIDIA", "nvidia", "wd5", "nvidia", "NVIDIAExternalCareerSite"),
    WorkdayTenant("Salesforce", "salesforce", "wd12", "salesforce", "External_Career_Site"),
    WorkdayTenant("Adobe", "adobe", "wd5", "adobe", "external_experienced"),
    WorkdayTenant("Boeing", "boeing", "wd1", "boeing", "EXTERNAL_CAREERS"),
    WorkdayTenant("Comcast", "comcastcareers", "wd5", "comcast", "Comcast_Careers"),
    WorkdayTenant("HP", "hp", "wd5", "hp", "ExternalCareerSite"),
]


def _strip_html(text: str | None) -> str | None:
    """Workday returns HTML in jobDescription; reduce to plain-ish text."""
    if not text:
        return text
    s = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    s = re.sub(r"</p>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</li>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    # Decode the most common entities; full unescape is overkill for our use.
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


_RELATIVE_RE = re.compile(
    r"posted\s+(\d+)\+?\s+(minute|hour|day|week|month)s?\s+ago",
    re.IGNORECASE,
)


def _parse_posted_on(posted_on: str | None) -> datetime:
    """Workday gives 'Posted 2 Days Ago' / 'Posted Today' / 'Posted Yesterday'.
    Convert to an absolute UTC timestamp for scraped_at, using `now` as the
    reference. Falls back to now() on unparseable strings."""
    now = datetime.now(timezone.utc)
    if not posted_on:
        return now
    s = posted_on.strip()
    low = s.lower()
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = _RELATIVE_RE.search(s)
    if not m:
        return now
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("minute"):
        return now - timedelta(minutes=n)
    if unit.startswith("hour"):
        return now - timedelta(hours=n)
    if unit.startswith("day"):
        return now - timedelta(days=n)
    if unit.startswith("week"):
        return now - timedelta(weeks=n)
    if unit.startswith("month"):
        return now - timedelta(days=n * 30)
    return now


async def _fetch_jobs_page(
    client: httpx.AsyncClient,
    tenant: WorkdayTenant,
    keyword: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """POST one page of the CXS jobs list. Returns (postings, total) or ([],0)
    on error so the orchestrator can keep going across other tenants."""
    body: dict[str, Any] = {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": keyword or "",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # Workday tends to 403 default-httpx; mimic a real browser referer.
        "Referer": tenant.base_host + "/" + tenant.site,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ),
    }
    try:
        resp = await client.post(tenant.jobs_url, json=body, headers=headers)
        if resp.status_code != 200:
            return [], 0
        data = resp.json()
        return data.get("jobPostings", []), int(data.get("total", 0))
    except (httpx.HTTPError, ValueError):
        return [], 0


async def _fetch_job_description(
    client: httpx.AsyncClient,
    tenant: WorkdayTenant,
    external_path: str,
) -> str | None:
    """Fetch one job's full description (HTML, then stripped)."""
    headers = {
        "Accept": "application/json",
        "Referer": tenant.base_host + "/" + tenant.site,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ),
    }
    try:
        resp = await client.get(tenant.detail_url(external_path), headers=headers)
        if resp.status_code != 200:
            return None
        info = resp.json().get("jobPostingInfo") or {}
        return _strip_html(info.get("jobDescription"))
    except (httpx.HTTPError, ValueError):
        return None


def _parse_one(
    raw: dict[str, Any],
    tenant: WorkdayTenant,
    description: str | None,
) -> NormalizedListing | None:
    title = raw.get("title")
    external_path = raw.get("externalPath")
    if not (title and external_path):
        return None

    source_id = raw.get("jobRequisitionId") or external_path
    location = raw.get("locationsText") or None
    scraped_at = _parse_posted_on(raw.get("postedOn"))

    return NormalizedListing(
        source="workday",
        source_id=str(source_id),
        source_url=tenant.public_url(external_path),
        company=tenant.company_label,
        title=title,
        location=location,
        description_raw=description,
        scraped_at=scraped_at,
    )


@register_connector
class WorkdayConnector(JobConnector):
    source_name = "workday"

    DEFAULT_TENANTS: ClassVar[list[WorkdayTenant]] = DEFAULT_TENANTS

    def __init__(self, tenants: list[WorkdayTenant] | None = None):
        self.tenants = tenants or list(DEFAULT_TENANTS)

    async def _fetch_for_tenant(
        self,
        client: httpx.AsyncClient,
        tenant: WorkdayTenant,
        keyword: str | None,
        max_per_tenant: int,
    ) -> list[NormalizedListing]:
        postings, _ = await _fetch_jobs_page(
            client, tenant, keyword, offset=0, limit=min(max_per_tenant, PAGE_SIZE)
        )
        if not postings:
            return []

        # Fetch full description per posting (Workday list omits it).
        # Cap concurrency per tenant to avoid getting flagged.
        sem = asyncio.Semaphore(3)

        async def _with_desc(p: dict[str, Any]) -> NormalizedListing | None:
            async with sem:
                desc = await _fetch_job_description(
                    client, tenant, p.get("externalPath", "")
                )
            return _parse_one(p, tenant, desc)

        results = await asyncio.gather(*(_with_desc(p) for p in postings[:max_per_tenant]))
        return [r for r in results if r is not None]

    async def fetch(
        self,
        keyword: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[NormalizedListing]:
        # Split max_results roughly evenly across tenants — caller wants
        # diversity, not all-from-one.
        per_tenant = max(2, max_results // max(1, len(self.tenants)))

        sem = asyncio.Semaphore(DEFAULT_CONCURRENCY)

        async def _bounded(client, tenant):
            async with sem:
                return await self._fetch_for_tenant(client, tenant, keyword, per_tenant)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            grouped = await asyncio.gather(
                *(_bounded(client, t) for t in self.tenants)
            )

        flat = [item for group in grouped for item in group]

        if location:
            loc_lower = location.lower()
            flat = [
                lst for lst in flat
                if lst.location and loc_lower in lst.location.lower()
            ]

        flat.sort(key=lambda x: x.scraped_at, reverse=True)
        return flat[:max_results]
