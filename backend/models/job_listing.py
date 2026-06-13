from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class JobListing(Base, TimestampMixin):
    """A normalized job posting from any connector (Adzuna, Greenhouse, Lever, Workday).

    Uniqueness: (source, source_id) — same posting from same source replaces in place.
    """

    __tablename__ = "job_listings"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_job_listings_source_sourceid"),
        CheckConstraint(
            "status IN ('new', 'saved', 'applied', 'rejected', 'interviewing', 'dismissed')",
            name="ck_job_listings_status",
        ),
        CheckConstraint(
            "sponsorship_status IS NULL OR "
            "sponsorship_status IN ('sponsors', 'no_sponsorship', 'us_citizen_only', 'unclear')",
            name="ck_job_listings_sponsorship_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- provenance ---
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- listing fields ---
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_clean: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- match scoring ---
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # --- user-side state ---
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", server_default="new"
    )

    # --- timing ---
    scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- sponsorship signals (M2) ---
    sponsorship_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sponsorship_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    sponsorship_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    h1b_lca_count_recent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    h1b_lca_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpt_opt_friendly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
