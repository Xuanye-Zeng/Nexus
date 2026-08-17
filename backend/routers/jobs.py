"""GET /api/jobs — list + stats + user application status for the frontend.

Wraps the same query the CLI uses but with pagination + total counts,
shape friendly to a React table component. Each listing row is annotated
with the current user's application status (via LEFT JOIN — null for
untracked listings).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import SessionLocal
from models import JobApplication, JobListing, User

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ALEX_EMAIL = "zeng.xuan@northeastern.edu"

# Downstream stages relative to the pipeline — moving to any of these implies
# the user has ACTUALLY submitted an application, so we stamp `applied_at`.
_APPLIED_STAGES = {"applied", "interviewing", "offer", "rejected"}
_ALL_STATUSES: tuple[str, ...] = (
    "saved",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
)


def next_applied_at(
    current: datetime | None, new_status: str, now: datetime
) -> datetime | None:
    """Sticky applied_at: once stamped, never resets.

    Extracted so it can be pinned by pytest without spinning up a DB — the
    endpoint's job is DB I/O; the *rule* about when to stamp lives here.
    """
    if current is not None:
        return current
    if new_status in _APPLIED_STAGES:
        return now
    return None


class UserStatus(BaseModel):
    status: str
    applied_at: datetime | None
    updated_at: datetime | None
    notes: str | None = None


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
    user_status: UserStatus | None = None


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


async def _resolve_user_id(s: AsyncSession) -> UUID:
    """Single-user mode — resolves Alex until auth lands."""
    user = (
        await s.execute(select(User).where(User.email == ALEX_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(500, f"User {ALEX_EMAIL!r} not seeded")
    return user.id


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
    application_status: Literal[
        "saved", "applied", "interviewing", "offer", "rejected", "withdrawn", "any", "none"
    ] | None = Query(default=None, description="'any' = has any user status; 'none' = untracked"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobListPage:
    async with SessionLocal() as s:
        user_id = await _resolve_user_id(s)

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

        # Application-status filter: subquery against job_applications for
        # this user, then apply {any / none / <specific>}.
        if application_status is not None:
            app_ids = select(JobApplication.listing_id).where(
                JobApplication.user_id == user_id
            )
            if application_status == "any":
                base = base.where(JobListing.id.in_(app_ids))
            elif application_status == "none":
                base = base.where(JobListing.id.not_in(app_ids))
            else:
                app_ids = app_ids.where(JobApplication.status == application_status)
                base = base.where(JobListing.id.in_(app_ids))

        total = (await s.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

        stmt = base.order_by(
            JobListing.match_score.desc().nulls_last(),
            JobListing.sponsorship_confidence.desc().nulls_last(),
        ).limit(limit).offset(offset)
        rows = (await s.execute(stmt)).scalars().all()

        # Batch-load user's applications for THIS page only (avoid N+1).
        listing_ids = [r.id for r in rows]
        apps_by_listing: dict[UUID, JobApplication] = {}
        if listing_ids:
            app_rows = (
                await s.execute(
                    select(JobApplication).where(
                        JobApplication.user_id == user_id,
                        JobApplication.listing_id.in_(listing_ids),
                    )
                )
            ).scalars().all()
            apps_by_listing = {a.listing_id: a for a in app_rows}

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
                user_status=_serialize_status(apps_by_listing.get(r.id)),
            )
            for r in rows
        ],
    )


def _serialize_status(app: JobApplication | None) -> UserStatus | None:
    if app is None:
        return None
    return UserStatus(
        status=app.status,
        applied_at=app.applied_at,
        updated_at=app.updated_at,
        notes=app.notes,
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


# ---------- application status (R4) ----------


class StatusUpsertBody(BaseModel):
    status: Literal[
        "saved", "applied", "interviewing", "offer", "rejected", "withdrawn"
    ]
    notes: str | None = None


class ApplicationOut(BaseModel):
    listing_id: str
    company: str
    title: str
    source_url: str | None
    match_score: float | None
    sponsorship_status: str | None
    status: str
    applied_at: datetime | None
    updated_at: datetime | None
    notes: str | None


class ApplicationCounts(BaseModel):
    by_status: dict[str, int]
    total_tracked: int
    applied_last_7_days: int
    applied_last_30_days: int


@router.put("/{listing_id}/status", response_model=UserStatus)
async def upsert_status(
    listing_id: UUID,
    body: StatusUpsertBody,
) -> UserStatus:
    """Idempotent upsert of the current user's application status for one
    listing. First transition INTO an applied-family stage stamps
    `applied_at`; reverting to `saved` / `withdrawn` does not reset it."""
    async with SessionLocal() as s:
        user_id = await _resolve_user_id(s)

        # Confirm the listing exists — surface 404 cleanly instead of a raw
        # FK violation from the DB.
        listing = (
            await s.execute(select(JobListing).where(JobListing.id == listing_id))
        ).scalar_one_or_none()
        if listing is None:
            raise HTTPException(404, f"listing {listing_id} not found")

        existing = (
            await s.execute(
                select(JobApplication).where(
                    JobApplication.user_id == user_id,
                    JobApplication.listing_id == listing_id,
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if existing is None:
            app = JobApplication(
                user_id=user_id,
                listing_id=listing_id,
                status=body.status,
                notes=body.notes,
                applied_at=next_applied_at(None, body.status, now),
            )
            s.add(app)
        else:
            existing.status = body.status
            if body.notes is not None:
                existing.notes = body.notes
            existing.applied_at = next_applied_at(
                existing.applied_at, body.status, now
            )
            app = existing

        await s.commit()
        await s.refresh(app)
        return _serialize_status(app)  # type: ignore[return-value]


@router.delete("/{listing_id}/status", status_code=204)
async def clear_status(listing_id: UUID) -> None:
    """Untrack a listing — remove the JobApplication row entirely.
    Idempotent: no-op if the listing was never tracked."""
    async with SessionLocal() as s:
        user_id = await _resolve_user_id(s)
        row = (
            await s.execute(
                select(JobApplication).where(
                    JobApplication.user_id == user_id,
                    JobApplication.listing_id == listing_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            await s.delete(row)
            await s.commit()


@router.get("/applications", response_model=list[ApplicationOut])
async def list_applications(
    status: Literal[
        "saved", "applied", "interviewing", "offer", "rejected", "withdrawn"
    ] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ApplicationOut]:
    """Applications joined with their listing, sorted by most recently
    touched. Used by the "My applications" surface."""
    async with SessionLocal() as s:
        user_id = await _resolve_user_id(s)

        stmt = (
            select(JobApplication, JobListing)
            .join(JobListing, JobApplication.listing_id == JobListing.id)
            .where(JobApplication.user_id == user_id)
        )
        if status is not None:
            stmt = stmt.where(JobApplication.status == status)
        stmt = stmt.order_by(JobApplication.updated_at.desc()).limit(limit)

        rows = (await s.execute(stmt)).all()

    return [
        ApplicationOut(
            listing_id=str(app.listing_id),
            company=listing.company,
            title=listing.title,
            source_url=listing.source_url,
            match_score=listing.match_score,
            sponsorship_status=listing.sponsorship_status,
            status=app.status,
            applied_at=app.applied_at,
            updated_at=app.updated_at,
            notes=app.notes,
        )
        for app, listing in rows
    ]


@router.get("/applications/counts", response_model=ApplicationCounts)
async def application_counts() -> ApplicationCounts:
    """KPIs for the Dashboard: total tracked + per-status breakdown +
    weekly / monthly application cadence."""
    async with SessionLocal() as s:
        user_id = await _resolve_user_id(s)

        by_status_rows = (
            await s.execute(
                select(JobApplication.status, func.count(JobApplication.id))
                .where(JobApplication.user_id == user_id)
                .group_by(JobApplication.status)
            )
        ).all()
        by_status = {status: 0 for status in _ALL_STATUSES}
        by_status.update({s_: int(c) for s_, c in by_status_rows})

        total_tracked = int(sum(by_status.values()))

        now = datetime.now(UTC)
        week_ago = now - _seconds(7 * 24 * 3600)
        month_ago = now - _seconds(30 * 24 * 3600)

        applied_7d = (
            await s.execute(
                select(func.count(JobApplication.id))
                .where(
                    JobApplication.user_id == user_id,
                    JobApplication.applied_at.is_not(None),
                    JobApplication.applied_at >= week_ago,
                )
            )
        ).scalar() or 0
        applied_30d = (
            await s.execute(
                select(func.count(JobApplication.id))
                .where(
                    JobApplication.user_id == user_id,
                    JobApplication.applied_at.is_not(None),
                    JobApplication.applied_at >= month_ago,
                )
            )
        ).scalar() or 0

    return ApplicationCounts(
        by_status=by_status,
        total_tracked=total_tracked,
        applied_last_7_days=int(applied_7d),
        applied_last_30_days=int(applied_30d),
    )


def _seconds(sec: int):
    from datetime import timedelta

    return timedelta(seconds=sec)
