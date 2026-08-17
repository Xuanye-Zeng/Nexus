"""User-facing status flow attached to a `job_listings` row.

One row per (user, listing) — the pair is unique. Status transitions are
free-form (any → any); we don't enforce a state machine because the user
is the sole authority and reality has plenty of "applied then withdrew
then re-applied" churn. `applied_at` is set once, on the first move to
'applied' or downstream; `updated_at` moves on every change so we can
sort "recently touched" and show weekly-application counts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class JobApplication(Base, TimestampMixin):
    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", name="uq_job_applications_user_listing"),
        CheckConstraint(
            "status IN ('saved', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn')",
            name="ck_job_applications_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set on first move into 'applied' (or any downstream stage). Sticky —
    # even if the user reverts back to 'saved', the fact "you actually
    # applied at time T" is preserved for the weekly-cadence KPI.
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # updated_at is per-row here (TimestampMixin only provides created_at)
    # because the "recently touched" ordering on the applications list
    # depends on updates, not first-write.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
