"""pgvector cosine-distance retrieval over resume_sections."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ResumeSection
from services.embedding import embed_text


@dataclass
class RankedSection:
    section: ResumeSection
    distance: float  # cosine distance: 0 = identical, 2 = opposite


async def top_k_sections_for_jd(
    session: AsyncSession,
    jd_text: str,
    profile_id: uuid.UUID,
    k: int = 12,
) -> list[RankedSection]:
    """Return resume sections ranked by cosine distance to the JD embedding.

    Smaller distance = more semantically similar.
    """
    jd_vec = embed_text(jd_text)

    stmt = (
        select(
            ResumeSection,
            ResumeSection.embedding.cosine_distance(jd_vec).label("distance"),
        )
        .where(ResumeSection.profile_id == profile_id)
        .where(ResumeSection.embedding.is_not(None))
        .order_by(ResumeSection.embedding.cosine_distance(jd_vec))
        .limit(k)
    )
    result = await session.execute(stmt)
    return [
        RankedSection(section=row.ResumeSection, distance=float(row.distance))
        for row in result.all()
    ]
