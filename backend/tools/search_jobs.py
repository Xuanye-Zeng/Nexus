"""search_jobs tool — query the job_listings table with filters."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from db import SessionLocal
from models import JobListing

from .registry import register_tool


@register_tool("search_jobs")
async def search_jobs(args: dict[str, Any]) -> dict[str, Any]:
    """Filter + rank job_listings.

    Accepted args:
      keyword, location, company, source, sponsors_only (bool),
      min_score (float), min_confidence (float), limit (int, default 10).

    Returns a dict with a `listings` array suitable for direct rendering.
    """
    keyword = args.get("keyword")
    location = args.get("location")
    company = args.get("company")
    source = args.get("source")
    sponsors_only = bool(args.get("sponsors_only", False))
    min_score = args.get("min_score")
    min_confidence = args.get("min_confidence")
    limit = int(args.get("limit", 10))

    stmt = select(JobListing)

    if sponsors_only:
        stmt = stmt.where(JobListing.sponsorship_status == "sponsors")
    else:
        # default: hide explicit denials even when user didn't ask
        stmt = stmt.where(
            or_(
                JobListing.sponsorship_status.is_(None),
                JobListing.sponsorship_status.not_in(
                    ("no_sponsorship", "us_citizen_only")
                ),
            )
        )

    if keyword:
        stmt = stmt.where(
            or_(
                JobListing.title.ilike(f"%{keyword}%"),
                JobListing.description_clean.ilike(f"%{keyword}%"),
            )
        )
    if location:
        stmt = stmt.where(JobListing.location.ilike(f"%{location}%"))
    if company:
        stmt = stmt.where(JobListing.company.ilike(f"%{company}%"))
    if source:
        stmt = stmt.where(JobListing.source == source)
    if min_score is not None:
        stmt = stmt.where(JobListing.match_score >= float(min_score))
    if min_confidence is not None:
        stmt = stmt.where(JobListing.sponsorship_confidence >= float(min_confidence))

    stmt = stmt.order_by(
        JobListing.match_score.desc().nulls_last(),
        JobListing.sponsorship_confidence.desc().nulls_last(),
    ).limit(limit)

    async with SessionLocal() as s:
        rows = (await s.execute(stmt)).scalars().all()

    return {
        "count": len(rows),
        "filters": {
            k: v
            for k, v in {
                "keyword": keyword,
                "location": location,
                "company": company,
                "source": source,
                "sponsors_only": sponsors_only,
                "min_score": min_score,
                "min_confidence": min_confidence,
                "limit": limit,
            }.items()
            if v is not None and v is not False
        },
        "listings": [
            {
                "id": str(r.id),
                "source": r.source,
                "company": r.company,
                "title": r.title,
                "location": r.location,
                "url": r.source_url,
                "match_score": r.match_score,
                "sponsorship_status": r.sponsorship_status,
                "sponsorship_confidence": r.sponsorship_confidence,
                "sponsorship_evidence": r.sponsorship_evidence,
                "h1b_lca_count_recent": r.h1b_lca_count_recent,
                "cpt_opt_friendly": r.cpt_opt_friendly,
            }
            for r in rows
        ],
    }
