from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Email(Base, TimestampMixin):
    """A normalized email message, sourced from Microsoft Graph or Gmail API.

    Uniqueness: (user_id, source, message_id) — same message from same source
    upserts in place. The classifier writes importance + category; the linked
    application id is set when an inbound sender matches a known company.
    """

    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "message_id",
            name="uq_emails_user_source_msg",
        ),
        CheckConstraint(
            "source IN ('outlook', 'gmail')",
            name="ck_emails_source",
        ),
        CheckConstraint(
            "importance_score IS NULL OR (importance_score >= 1 AND importance_score <= 5)",
            name="ck_emails_importance_range",
        ),
        CheckConstraint(
            "category IS NULL OR category IN ('interview', 'recruiter', 'rejection', "
            "'offer', 'spam', 'newsletter', 'application_confirmation', 'other')",
            name="ck_emails_category",
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

    # provenance
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    # Microsoft Graph and Gmail return rich threading; we just keep the
    # conversation/thread id verbatim for later linking.
    thread_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # core fields
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_full: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # classifier output
    importance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classifier_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    classifier_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # linkage to job applications (set when sender matches a known company)
    linked_job_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_listings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # for semantic search across emails (future "find that interview email" feature)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
