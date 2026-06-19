from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AgentRun(Base, TimestampMixin):
    """One Master Agent invocation — input, routed intent, tool args + result,
    latency, error, and (optional) external trace id. Powers the "what did the
    agent do?" audit surface + future LangSmith linking.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "module IN ('master_agent', 'resume_customizer', 'email_triage', 'job_board')",
            name="ck_agent_runs_module",
        ),
        CheckConstraint(
            "status IN ('success', 'clarify', 'error', 'tool_error')",
            name="ck_agent_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    # input / output — capped at sensible sizes; the full payloads live in
    # downstream observability (LangSmith trace, app logs).
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_args: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tool_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    classifier_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    langsmith_trace_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
