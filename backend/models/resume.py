from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class ResumeProfile(Base, TimestampMixin):
    __tablename__ = "resume_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "version", name="uq_resume_profiles_user_version"
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
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped[User] = relationship(back_populates="resume_profiles")
    sections: Mapped[list[ResumeSection]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class ResumeSection(Base, TimestampMixin):
    __tablename__ = "resume_sections"
    __table_args__ = (
        CheckConstraint(
            "section_type IN ('project', 'experience', 'skill', 'education')",
            name="ck_resume_sections_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(768), nullable=True
    )

    profile: Mapped[ResumeProfile] = relationship(back_populates="sections")
