"""POST /api/agent — natural-language entry to the Master Agent.

One turn per request. Multi-turn conversation memory would live in this
router (DB-backed session) once we have user auth; v1 is single-turn.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from agents import run_master_agent
from db import SessionLocal
from models import AgentRun

router = APIRouter(prefix="/api", tags=["master_agent"])


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural-language request")


class AgentResponse(BaseModel):
    response: str
    intent: str
    tool_args: dict[str, Any] = {}
    tool_result: Any = None
    classifier_reasoning: str = ""
    error: str = ""


@router.post("/agent", response_model=AgentResponse)
async def agent(req: AgentRequest) -> AgentResponse:
    result = await run_master_agent(req.message)
    return AgentResponse(
        response=result.response,
        intent=result.intent,
        tool_args=result.tool_args,
        tool_result=result.tool_result,
        classifier_reasoning=result.classifier_reasoning,
        error=result.error,
    )


# ---------- agent_runs audit surface ----------


class AgentRunOut(BaseModel):
    id: str
    module: str
    intent: str | None
    status: str
    input_summary: str | None
    response: str | None
    classifier_reasoning: str | None
    error: str | None
    latency_ms: int | None
    langsmith_trace_id: str | None
    created_at: datetime


class AgentRunsPage(BaseModel):
    total: int
    items: list[AgentRunOut]


class AgentRunsStats(BaseModel):
    total: int
    by_intent: dict[str, int]
    by_status: dict[str, int]
    avg_latency_ms: float | None
    p95_latency_ms: float | None


@router.get("/agent/runs", response_model=AgentRunsPage)
async def list_agent_runs(
    intent: str | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AgentRunsPage:
    async with SessionLocal() as s:
        base = select(AgentRun)
        if intent:
            base = base.where(AgentRun.intent == intent)
        if status:
            base = base.where(AgentRun.status == status)

        total = (
            await s.execute(select(func.count()).select_from(base.subquery()))
        ).scalar() or 0

        rows = (
            await s.execute(
                base.order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()

    return AgentRunsPage(
        total=int(total),
        items=[
            AgentRunOut(
                id=str(r.id),
                module=r.module,
                intent=r.intent,
                status=r.status,
                input_summary=r.input_summary,
                response=r.response,
                classifier_reasoning=r.classifier_reasoning,
                error=r.error,
                latency_ms=r.latency_ms,
                langsmith_trace_id=r.langsmith_trace_id,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.get("/agent/runs/stats", response_model=AgentRunsStats)
async def agent_runs_stats() -> AgentRunsStats:
    async with SessionLocal() as s:
        total = (await s.execute(select(func.count(AgentRun.id)))).scalar() or 0

        by_intent_rows = (
            await s.execute(
                select(AgentRun.intent, func.count(AgentRun.id))
                .group_by(AgentRun.intent)
            )
        ).all()
        by_status_rows = (
            await s.execute(
                select(AgentRun.status, func.count(AgentRun.id))
                .group_by(AgentRun.status)
            )
        ).all()

        avg_latency = (
            await s.execute(select(func.avg(AgentRun.latency_ms)))
        ).scalar()
        # Approximate p95 via percentile_cont — Postgres has it via the
        # `percentile_cont` ordered-set aggregate.
        p95 = (
            await s.execute(
                select(
                    func.percentile_cont(0.95).within_group(
                        AgentRun.latency_ms.asc()
                    )
                ).where(AgentRun.latency_ms.is_not(None))
            )
        ).scalar()

    return AgentRunsStats(
        total=int(total),
        by_intent={(i or "unknown"): int(c) for i, c in by_intent_rows},
        by_status={s_: int(c) for s_, c in by_status_rows},
        avg_latency_ms=float(avg_latency) if avg_latency is not None else None,
        p95_latency_ms=float(p95) if p95 is not None else None,
    )
