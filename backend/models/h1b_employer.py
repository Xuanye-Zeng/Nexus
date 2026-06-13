from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class H1BEmployer(Base, TimestampMixin):
    """Aggregated H-1B LCA filings per employer, ingested from DOL OFLC public CSV.

    Refreshed quarterly. employer_name_normalized is the lowercase, suffix-stripped
    (Inc/LLC/Corp/Co/Ltd) form used to join against JobListing.company.
    """

    __tablename__ = "h1b_employers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    employer_name_normalized: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    employer_name_display: Mapped[str] = mapped_column(String(512), nullable=False)

    lca_count_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lca_count_last_12mo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    most_recent_filing_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    most_recent_filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    top_job_titles: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
