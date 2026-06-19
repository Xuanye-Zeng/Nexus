"""GET /api/overview — aggregated dashboard stats for the home page."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from db import SessionLocal
from models import Email, H1BEmployer, JobListing, ResumeProfile, ResumeSection, User

router = APIRouter(prefix="/api/overview", tags=["overview"])

ALEX_EMAIL = "zeng.xuan@northeastern.edu"


class UserSummary(BaseModel):
    email: str
    name: str
    resume_version: int | None
    resume_label: str | None
    sections_count: int


class Counts(BaseModel):
    jobs_total: int
    jobs_sponsors: int
    jobs_unique_companies: int
    emails_total: int
    emails_unread: int
    emails_high_importance: int       # importance_score >= 4
    h1b_employers_total: int
    h1b_lcas_recent_total: int        # sum(lca_count_last_12mo)


class TopJob(BaseModel):
    id: str
    source: str
    company: str
    title: str
    location: str | None
    match_score: float | None
    sponsorship_status: str | None
    sponsorship_confidence: float | None
    h1b_lca_count_recent: int | None
    cpt_opt_friendly: bool | None
    source_url: str | None
    scraped_at: datetime | None


class UrgentEmail(BaseModel):
    id: str
    category: str | None
    importance_score: int | None
    sender_name: str | None
    sender: str | None
    subject: str | None
    received_at: datetime | None


class OverviewOut(BaseModel):
    user: UserSummary
    counts: Counts
    top_jobs: list[TopJob]
    urgent_emails: list[UrgentEmail]
    match_score_buckets: list[dict]   # [{label, count}] — 0.0-0.2, 0.2-0.4, ...
    sponsorship_breakdown: dict[str, int]
    source_breakdown: dict[str, int]


@router.get("", response_model=OverviewOut)
async def overview() -> OverviewOut:
    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()

        profile = (
            await s.execute(
                select(ResumeProfile)
                .where(ResumeProfile.user_id == user.id)
                .order_by(ResumeProfile.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        sections_count = 0
        if profile:
            sections_count = (
                await s.execute(
                    select(func.count(ResumeSection.id)).where(
                        ResumeSection.profile_id == profile.id
                    )
                )
            ).scalar() or 0

        jobs_total = (await s.execute(select(func.count(JobListing.id)))).scalar() or 0
        jobs_sponsors = (
            await s.execute(
                select(func.count(JobListing.id)).where(
                    JobListing.sponsorship_status == "sponsors"
                )
            )
        ).scalar() or 0
        jobs_unique_companies = (
            await s.execute(select(func.count(func.distinct(JobListing.company))))
        ).scalar() or 0

        emails_total = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id, Email.is_deleted.is_(False)
                )
            )
        ).scalar() or 0
        emails_unread = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id,
                    Email.is_deleted.is_(False),
                    Email.is_read.is_(False),
                )
            )
        ).scalar() or 0
        emails_high = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id,
                    Email.is_deleted.is_(False),
                    Email.importance_score >= 4,
                )
            )
        ).scalar() or 0

        h1b_total = (await s.execute(select(func.count(H1BEmployer.id)))).scalar() or 0
        h1b_lcas = (
            await s.execute(select(func.sum(H1BEmployer.lca_count_last_12mo)))
        ).scalar() or 0

        # Dashboard primary feed: fresh + sponsor-friendly. Hard-filter denials
        # (no_sponsorship + us_citizen_only) since the dashboard is the
        # international-student daily view. Sort by scraped_at DESC primarily so
        # the user sees newly-posted jobs first; match_score is the tiebreaker.
        top_jobs_rows = (
            await s.execute(
                select(JobListing)
                .where(
                    JobListing.sponsorship_status.is_(None)
                    | JobListing.sponsorship_status.in_(("sponsors", "unclear"))
                )
                .order_by(
                    JobListing.scraped_at.desc().nulls_last(),
                    JobListing.match_score.desc().nulls_last(),
                )
                .limit(15)
            )
        ).scalars().all()

        urgent_emails_rows = (
            await s.execute(
                select(Email)
                .where(
                    Email.user_id == user.id,
                    Email.is_deleted.is_(False),
                    Email.importance_score >= 3,
                )
                .order_by(
                    Email.importance_score.desc(),
                    Email.received_at.desc().nulls_last(),
                )
                .limit(5)
            )
        ).scalars().all()

        # Match score distribution (5 buckets, 0.0-1.0)
        buckets = [
            {"label": "0.0-0.2", "min": 0.0, "max": 0.2},
            {"label": "0.2-0.4", "min": 0.2, "max": 0.4},
            {"label": "0.4-0.6", "min": 0.4, "max": 0.6},
            {"label": "0.6-0.8", "min": 0.6, "max": 0.8},
            {"label": "0.8-1.0", "min": 0.8, "max": 1.01},
        ]
        out_buckets = []
        for b in buckets:
            count = (
                await s.execute(
                    select(func.count(JobListing.id)).where(
                        JobListing.match_score >= b["min"],
                        JobListing.match_score < b["max"],
                    )
                )
            ).scalar() or 0
            out_buckets.append({"label": b["label"], "count": int(count)})

        by_sponsor_rows = (
            await s.execute(
                select(JobListing.sponsorship_status, func.count(JobListing.id))
                .group_by(JobListing.sponsorship_status)
            )
        ).all()

        by_source_rows = (
            await s.execute(
                select(JobListing.source, func.count(JobListing.id)).group_by(JobListing.source)
            )
        ).all()

    return OverviewOut(
        user=UserSummary(
            email=user.email,
            name=user.name,
            resume_version=profile.version if profile else None,
            resume_label=profile.label if profile else None,
            sections_count=int(sections_count),
        ),
        counts=Counts(
            jobs_total=int(jobs_total),
            jobs_sponsors=int(jobs_sponsors),
            jobs_unique_companies=int(jobs_unique_companies),
            emails_total=int(emails_total),
            emails_unread=int(emails_unread),
            emails_high_importance=int(emails_high),
            h1b_employers_total=int(h1b_total),
            h1b_lcas_recent_total=int(h1b_lcas),
        ),
        top_jobs=[
            TopJob(
                id=str(j.id),
                source=j.source,
                company=j.company,
                title=j.title,
                location=j.location,
                match_score=j.match_score,
                sponsorship_status=j.sponsorship_status,
                sponsorship_confidence=j.sponsorship_confidence,
                h1b_lca_count_recent=j.h1b_lca_count_recent,
                cpt_opt_friendly=j.cpt_opt_friendly,
                source_url=j.source_url,
                scraped_at=j.scraped_at,
            )
            for j in top_jobs_rows
        ],
        urgent_emails=[
            UrgentEmail(
                id=str(e.id),
                category=e.category,
                importance_score=e.importance_score,
                sender_name=e.sender_name,
                sender=e.sender,
                subject=e.subject,
                received_at=e.received_at,
            )
            for e in urgent_emails_rows
        ],
        match_score_buckets=out_buckets,
        sponsorship_breakdown={(s_ or "unclassified"): int(c) for s_, c in by_sponsor_rows},
        source_breakdown={src: int(c) for src, c in by_source_rows},
    )
