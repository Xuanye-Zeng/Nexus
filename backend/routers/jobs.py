"""GET /api/jobs — list + stats for the frontend.

Wraps the same query the CLI uses but with pagination + total counts,
shape friendly to a React table component.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import SessionLocal
from models import JobListing

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: str
    source: str
    company: str
    title: str
    location: str | None
    source_url: str | None
    match_score: float | None
    sponsorship_status: str | None
    sponsorship_confidence: float | None
    sponsorship_evidence: str | None
    h1b_lca_count_recent: int | None
    cpt_opt_friendly: bool | None


class JobListPage(BaseModel):
    total: int
    items: list[JobOut]


class JobStats(BaseModel):
    total: int
    by_source: dict[str, int]
    by_sponsorship: dict[str, int]
    by_company_top: list[dict]  # [{company, count}]
    avg_match_score: float | None
    avg_match_score_sponsors_only: float | None


async def _get_session() -> AsyncSession:
    async with SessionLocal() as s:
        yield s


@router.get("", response_model=JobListPage)
async def list_jobs(
    keyword: str | None = None,
    location: str | None = None,
    company: str | None = None,
    source: str | None = None,
    sponsorship_status: Literal[
        "sponsors", "no_sponsorship", "us_citizen_only", "unclear"
    ] | None = None,
    hide_denials: bool = Query(default=True, description="Hide no_sponsorship + us_citizen_only by default"),
    min_score: float | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobListPage:
    async with SessionLocal() as s:
        base = select(JobListing)
        if sponsorship_status is not None:
            base = base.where(JobListing.sponsorship_status == sponsorship_status)
        elif hide_denials:
            base = base.where(
                or_(
                    JobListing.sponsorship_status.is_(None),
                    JobListing.sponsorship_status.not_in(("no_sponsorship", "us_citizen_only")),
                )
            )
        if keyword:
            base = base.where(
                or_(
                    JobListing.title.ilike(f"%{keyword}%"),
                    JobListing.description_clean.ilike(f"%{keyword}%"),
                )
            )
        if location:
            base = base.where(JobListing.location.ilike(f"%{location}%"))
        if company:
            base = base.where(JobListing.company.ilike(f"%{company}%"))
        if source:
            base = base.where(JobListing.source == source)
        if min_score is not None:
            base = base.where(JobListing.match_score >= min_score)

        total = (await s.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

        stmt = base.order_by(
            JobListing.match_score.desc().nulls_last(),
            JobListing.sponsorship_confidence.desc().nulls_last(),
        ).limit(limit).offset(offset)
        rows = (await s.execute(stmt)).scalars().all()

    return JobListPage(
        total=total,
        items=[
            JobOut(
                id=str(r.id),
                source=r.source,
                company=r.company,
                title=r.title,
                location=r.location,
                source_url=r.source_url,
                match_score=r.match_score,
                sponsorship_status=r.sponsorship_status,
                sponsorship_confidence=r.sponsorship_confidence,
                sponsorship_evidence=r.sponsorship_evidence,
                h1b_lca_count_recent=r.h1b_lca_count_recent,
                cpt_opt_friendly=r.cpt_opt_friendly,
            )
            for r in rows
        ],
    )


@router.get("/stats", response_model=JobStats)
async def stats() -> JobStats:
    async with SessionLocal() as s:
        total = (await s.execute(select(func.count(JobListing.id)))).scalar() or 0

        by_source_rows = (
            await s.execute(
                select(JobListing.source, func.count(JobListing.id)).group_by(JobListing.source)
            )
        ).all()
        by_source = {src: int(cnt) for src, cnt in by_source_rows}

        by_sponsorship_rows = (
            await s.execute(
                select(JobListing.sponsorship_status, func.count(JobListing.id)).group_by(
                    JobListing.sponsorship_status
                )
            )
        ).all()
        by_sponsorship = {(s_ or "unclassified"): int(cnt) for s_, cnt in by_sponsorship_rows}

        top_companies = (
            await s.execute(
                select(JobListing.company, func.count(JobListing.id).label("c"))
                .group_by(JobListing.company)
                .order_by(func.count(JobListing.id).desc())
                .limit(10)
            )
        ).all()

        avg_score = (
            await s.execute(select(func.avg(JobListing.match_score)))
        ).scalar()

        avg_score_sp = (
            await s.execute(
                select(func.avg(JobListing.match_score)).where(
                    JobListing.sponsorship_status == "sponsors"
                )
            )
        ).scalar()

    return JobStats(
        total=int(total),
        by_source=by_source,
        by_sponsorship=by_sponsorship,
        by_company_top=[{"company": c, "count": int(cnt)} for c, cnt in top_companies],
        avg_match_score=float(avg_score) if avg_score is not None else None,
        avg_match_score_sponsors_only=float(avg_score_sp) if avg_score_sp is not None else None,
    )
