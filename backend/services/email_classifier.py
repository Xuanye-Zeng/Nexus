"""Classify a single email body using the email_classifier prompt.

Reusable by:
  - scripts/run_email_classifier.py (fixture benchmark)
  - scripts/sync_emails_*.py (when OAuth comes online)
  - tools/email_triage.py (agent-triggered re-classify of one email)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PromptTemplate
from services.llm import get_llm


@dataclass(frozen=True)
class EmailClassification:
    category: str
    importance_score: int
    confidence: float
    reasoning: str
    prompt_version: int


VALID_CATEGORIES = {
    "interview",
    "offer",
    "recruiter",
    "application_confirmation",
    "rejection",
    "newsletter",
    "spam",
    "other",
}


def _parse_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    return json.loads(s)


async def _active_prompt(s: AsyncSession) -> PromptTemplate:
    row = (
        await s.execute(
            select(PromptTemplate)
            .where(
                PromptTemplate.name == "email_classifier",
                PromptTemplate.is_active.is_(True),
            )
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
    ).scalar_one()
    return row


def _build_user_msg(
    *,
    sender: str | None,
    subject: str | None,
    received_at: str | None,
    body: str | None,
) -> str:
    parts = []
    if sender:
        parts.append(f"## From: {sender}")
    if subject:
        parts.append(f"## Subject: {subject}")
    if received_at:
        parts.append(f"## Received: {received_at}")
    if body:
        parts.append(f"## Body:\n{body}")
    return "\n".join(parts)


async def classify_email(
    s: AsyncSession,
    *,
    sender: str | None = None,
    subject: str | None = None,
    received_at: str | None = None,
    body: str | None = None,
) -> EmailClassification:
    """Run the active email_classifier prompt on a single email's content."""
    prompt = await _active_prompt(s)
    llm = get_llm("email_classifier")

    user_msg = _build_user_msg(
        sender=sender, subject=subject, received_at=received_at, body=body
    )
    resp = llm.invoke(
        [SystemMessage(content=prompt.content), HumanMessage(content=user_msg)]
    )

    try:
        out = _parse_json(resp.content)
    except json.JSONDecodeError:
        # Fallback for malformed output: low-confidence "other".
        return EmailClassification(
            category="other",
            importance_score=3,
            confidence=0.0,
            reasoning="classifier returned non-JSON output; defaulting to other",
            prompt_version=prompt.version,
        )

    category = out.get("category", "other")
    if category not in VALID_CATEGORIES:
        category = "other"

    score = int(out.get("importance_score", 3))
    score = max(1, min(5, score))

    return EmailClassification(
        category=category,
        importance_score=score,
        confidence=float(out.get("confidence", 0.0)),
        reasoning=str(out.get("reasoning", ""))[:500],
        prompt_version=prompt.version,
    )
