"""triage_emails tool — list emails ranked by importance.

Default behavior: hide deleted, sort importance DESC then received_at DESC.
Filters mirror what the user can describe in natural language:
  category, min_importance, sender substring, unread_only, limit.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from db import SessionLocal
from models import Email, User

from .registry import register_tool

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
VALID_CATEGORIES = {
    "interview", "offer", "recruiter", "application_confirmation",
    "rejection", "newsletter", "spam", "other",
}


@register_tool("triage_emails")
async def triage_emails(args: dict[str, Any]) -> dict[str, Any]:
    """Rank inbox by importance + category.

    Args (all optional):
      category: substring/exact-match filter on the classifier category.
      min_importance: int 1-5 floor.
      sender: substring filter on the sender field.
      unread_only: bool, default false.
      include_deleted: bool, default false (hides soft-deleted by default).
      limit: int, default 20.
    """
    category = args.get("category")
    min_importance = args.get("min_importance")
    sender = args.get("sender")
    unread_only = bool(args.get("unread_only", False))
    include_deleted = bool(args.get("include_deleted", False))
    limit = int(args.get("limit", 20))

    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()

        stmt = select(Email).where(Email.user_id == user.id)
        if not include_deleted:
            stmt = stmt.where(Email.is_deleted.is_(False))
        if unread_only:
            stmt = stmt.where(Email.is_read.is_(False))
        if category:
            if category in VALID_CATEGORIES:
                stmt = stmt.where(Email.category == category)
            else:
                stmt = stmt.where(Email.category.ilike(f"%{category}%"))
        if min_importance is not None:
            stmt = stmt.where(Email.importance_score >= int(min_importance))
        if sender:
            stmt = stmt.where(Email.sender.ilike(f"%{sender}%"))

        stmt = stmt.order_by(
            Email.importance_score.desc().nulls_last(),
            Email.received_at.desc().nulls_last(),
        ).limit(limit)

        rows = (await s.execute(stmt)).scalars().all()

    return {
        "count": len(rows),
        "filters": {
            k: v for k, v in {
                "category": category,
                "min_importance": min_importance,
                "sender": sender,
                "unread_only": unread_only,
                "include_deleted": include_deleted,
                "limit": limit,
            }.items() if v is not None and v is not False
        },
        "emails": [
            {
                "id": str(r.id),
                "category": r.category,
                "importance_score": r.importance_score,
                "confidence": r.classifier_confidence,
                "reasoning": r.classifier_reasoning,
                "sender": r.sender,
                "sender_name": r.sender_name,
                "subject": r.subject,
                "body_preview": (r.body_preview or "")[:200],
                "received_at": r.received_at.isoformat() if r.received_at else None,
                "is_read": r.is_read,
            }
            for r in rows
        ],
    }
