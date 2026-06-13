"""delete_emails tool — soft-delete emails matching a filter.

Sets is_deleted=true on the matching rows. Until OAuth lands the action is
local-only (does NOT call back to the Microsoft Graph or Gmail API);
that's a v1.5 wiring task.

Default safety:
  - Requires at least one filter (category / sender / id) — refuses bare
    "delete everything" calls.
  - Capped at 200 rows per invocation.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select, update

from db import SessionLocal
from models import Email, User

from .registry import register_tool

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
MAX_DELETE = 200


@register_tool("delete_emails")
async def delete_emails(args: dict[str, Any]) -> dict[str, Any]:
    """Soft-delete matching emails.

    Args (at least ONE of category / sender / email_id required):
      category: classifier category (e.g. "rejection", "newsletter", "spam").
      sender: substring on sender (e.g. "indeed.com").
      email_id: UUID of a single email.
      max_importance: int — also gates by `importance_score <= this` (default null = no cap).

    Returns: {deleted: int, ids: [list of soft-deleted email ids]}.
    """
    category = args.get("category")
    sender = args.get("sender")
    email_id = args.get("email_id")
    max_importance = args.get("max_importance")

    if not (category or sender or email_id):
        return {
            "error": (
                "delete_emails requires at least one of `category`, `sender`, "
                "or `email_id`. Refusing to delete without a filter."
            )
        }

    async with SessionLocal() as s:
        user = (
            await s.execute(select(User).where(User.email == ALEX_EMAIL))
        ).scalar_one()

        # First, identify the matching rows so we can report them.
        stmt = select(Email).where(
            Email.user_id == user.id,
            Email.is_deleted.is_(False),
        )
        if email_id:
            stmt = stmt.where(Email.id == email_id)
        if category:
            stmt = stmt.where(Email.category == category)
        if sender:
            stmt = stmt.where(Email.sender.ilike(f"%{sender}%"))
        if max_importance is not None:
            stmt = stmt.where(
                or_(
                    Email.importance_score.is_(None),
                    Email.importance_score <= int(max_importance),
                )
            )
        stmt = stmt.limit(MAX_DELETE)

        rows = (await s.execute(stmt)).scalars().all()
        ids = [str(r.id) for r in rows]

        if not ids:
            return {"deleted": 0, "ids": [], "filters": {k: v for k, v in args.items() if v}}

        await s.execute(
            update(Email)
            .where(Email.id.in_([r.id for r in rows]))
            .values(is_deleted=True)
        )
        await s.commit()

    return {
        "deleted": len(ids),
        "ids": ids,
        "filters": {k: v for k, v in args.items() if v},
        "note": "soft-delete only; Microsoft Graph / Gmail API delete will be wired with OAuth (v1.5).",
    }
