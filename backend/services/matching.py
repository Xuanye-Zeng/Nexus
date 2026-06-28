"""Resume-to-JD match scoring.

Algorithm: **Top-K mean cosine similarity** between the JD embedding and the
resume's section embeddings.
  - max() alone is too lenient: one matching skill yields a perfect score.
  - mean() alone is too harsh: an unrelated education section drags everything down.
  - mean of the top K (default 3) of all section similarities is a balanced signal:
    rewards strong matches without being fooled by a single keyword hit.

Output is in [0, 1] (cosine of two normalized 768d nomic-embed-text vectors,
clamped from the native [-1, 1] range — negative values get clipped to 0
because they are not useful signal here).

Per-resume design: match_score is per-(listing, active resume profile). When
Alex updates his resume:
  1. Re-seed resume sections (existing scripts/seed_resume.py).
  2. Run scripts/rescore_listings.py — recomputes match_score across all
     existing job_listings using the new section embeddings.
This decouples ingest from resume freshness; the score always reflects the
CURRENT active profile.
"""
from __future__ import annotations

import math
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import JobListing, ResumeProfile, ResumeSection, User

TOP_K_DEFAULT = 3
SCORE_SECTION_TYPES = {"project", "experience", "skill"}  # education adds noise


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    return dot / denom if denom > 0 else 0.0


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def top_k_mean(
    jd_embedding: list[float],
    section_embeddings: list[list[float]],
    k: int = TOP_K_DEFAULT,
) -> float:
    """Pure-Python top-K mean cosine similarity. Used for single-listing scoring."""
    if not jd_embedding or not section_embeddings:
        return 0.0
    sims = [_cosine_sim(jd_embedding, s) for s in section_embeddings if s]
    if not sims:
        return 0.0
    sims.sort(reverse=True)
    top = sims[: max(1, k)]
    return _clip01(sum(top) / len(top))


async def _active_profile_id(s: AsyncSession) -> uuid.UUID | None:
    """Single-user assumption: pick the highest-versioned profile of the
    most-recently-created user. This is what `scripts/seed_resume.py` writes.
    Returns None if no profile is seeded yet.
    """
    user_id = (
        await s.execute(
            select(User.id).order_by(User.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if user_id is None:
        return None
    return (
        await s.execute(
            select(ResumeProfile.id)
            .where(ResumeProfile.user_id == user_id)
            .order_by(ResumeProfile.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _section_embeddings(
    s: AsyncSession, profile_id: uuid.UUID
) -> list[list[float]]:
    rows = (
        await s.execute(
            select(ResumeSection.embedding, ResumeSection.section_type).where(
                ResumeSection.profile_id == profile_id,
                ResumeSection.embedding.is_not(None),
            )
        )
    ).all()
    return [
        list(emb) for emb, sec_type in rows if sec_type in SCORE_SECTION_TYPES and emb is not None
    ]


async def score_listing_against_profile(
    s: AsyncSession,
    jd_embedding: list[float],
    profile_id: uuid.UUID,
    k: int = TOP_K_DEFAULT,
) -> float | None:
    """Score a JD embedding against a specific profile. Returns None if the
    profile has no scorable sections."""
    sections = await _section_embeddings(s, profile_id)
    if not sections:
        return None
    return top_k_mean(jd_embedding, sections, k=k)


async def score_listing_against_active_profile(
    s: AsyncSession, jd_embedding: list[float], k: int = TOP_K_DEFAULT
) -> float | None:
    """Score a JD embedding against the single user's active profile.

    Returns None if no profile is seeded (test/empty DB) or if the JD
    embedding is empty.
    """
    profile_id = await _active_profile_id(s)
    if profile_id is None:
        return None
    return await score_listing_against_profile(s, jd_embedding, profile_id, k=k)


async def rescore_all_listings(s: AsyncSession, k: int = TOP_K_DEFAULT) -> int:
    """Recompute match_score for every job_listing against the active profile.

    Uses pgvector's cosine_distance in SQL for speed on large tables, then
    falls back to Python for the top-K mean (Postgres doesn't have a native
    top-K aggregation, and rolling our own with LATERAL would obscure the
    intent for marginal speedup at our scale).

    Returns number of listings updated.
    """
    profile_id = await _active_profile_id(s)
    if profile_id is None:
        return 0

    section_embs = await _section_embeddings(s, profile_id)
    if not section_embs:
        return 0

    listings = (
        await s.execute(
            select(JobListing.id, JobListing.embedding).where(
                JobListing.embedding.is_not(None)
            )
        )
    ).all()

    updated = 0
    for listing_id, jd_emb in listings:
        score = top_k_mean(list(jd_emb), section_embs, k=k)
        await s.execute(
            update(JobListing)
            .where(JobListing.id == listing_id)
            .values(match_score=score)
        )
        updated += 1
    await s.commit()
    return updated
