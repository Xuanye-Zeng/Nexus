"""GET /api/emails — list + stats for the frontend."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from db import SessionLocal
from models import Email, User

router = APIRouter(prefix="/api/emails", tags=["emails"])

ALEX_EMAIL = "zeng.xuan@northeastern.edu"


class EmailOut(BaseModel):
    id: str
    category: str | None
    importance_score: int | None
    confidence: float | None
    sender: str | None
    sender_name: str | None
    subject: str | None
    body_preview: str | None
    received_at: datetime | None
    is_read: bool
    is_deleted: bool


class EmailListPage(BaseModel):
    total: int
    items: list[EmailOut]


class EmailStats(BaseModel):
    total: int
    by_category: dict[str, int]
    by_importance: dict[str, int]
    unread: int
    deleted: int


@router.get("", response_model=EmailListPage)
async def list_emails(
    category: Literal[
        "interview", "offer", "recruiter", "application_confirmation",
        "rejection", "newsletter", "spam", "other",
    ] | None = None,
    min_importance: int | None = Query(default=None, ge=1, le=5),
    include_deleted: bool = False,
    unread_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EmailListPage:
    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()

        base = select(Email).where(Email.user_id == user.id)
        if not include_deleted:
            base = base.where(Email.is_deleted.is_(False))
        if unread_only:
            base = base.where(Email.is_read.is_(False))
        if category:
            base = base.where(Email.category == category)
        if min_importance:
            base = base.where(Email.importance_score >= min_importance)

        total = (
            await s.execute(select(func.count()).select_from(base.subquery()))
        ).scalar() or 0

        rows = (
            await s.execute(
                base.order_by(
                    Email.importance_score.desc().nulls_last(),
                    Email.received_at.desc().nulls_last(),
                ).limit(limit).offset(offset)
            )
        ).scalars().all()

    return EmailListPage(
        total=total,
        items=[
            EmailOut(
                id=str(r.id),
                category=r.category,
                importance_score=r.importance_score,
                confidence=r.classifier_confidence,
                sender=r.sender,
                sender_name=r.sender_name,
                subject=r.subject,
                body_preview=r.body_preview,
                received_at=r.received_at,
                is_read=r.is_read,
                is_deleted=r.is_deleted,
            )
            for r in rows
        ],
    )


@router.get("/stats", response_model=EmailStats)
async def stats() -> EmailStats:
    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()

        total = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id, Email.is_deleted.is_(False)
                )
            )
        ).scalar() or 0

        by_category_rows = (
            await s.execute(
                select(Email.category, func.count(Email.id))
                .where(Email.user_id == user.id, Email.is_deleted.is_(False))
                .group_by(Email.category)
            )
        ).all()

        by_importance_rows = (
            await s.execute(
                select(Email.importance_score, func.count(Email.id))
                .where(Email.user_id == user.id, Email.is_deleted.is_(False))
                .group_by(Email.importance_score)
            )
        ).all()

        unread = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id,
                    Email.is_deleted.is_(False),
                    Email.is_read.is_(False),
                )
            )
        ).scalar() or 0

        deleted = (
            await s.execute(
                select(func.count(Email.id)).where(
                    Email.user_id == user.id, Email.is_deleted.is_(True)
                )
            )
        ).scalar() or 0

    return EmailStats(
        total=int(total),
        by_category={(c or "uncategorized"): int(cnt) for c, cnt in by_category_rows},
        by_importance={str(s_ or "null"): int(cnt) for s_, cnt in by_importance_rows},
        unread=int(unread),
        deleted=int(deleted),
    )
