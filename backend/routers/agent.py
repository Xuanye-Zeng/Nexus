"""POST /api/agent — natural-language entry to the Master Agent.

One turn per request. Multi-turn conversation memory would live in this
router (DB-backed session) once we have user auth; v1 is single-turn.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents import run_master_agent

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
