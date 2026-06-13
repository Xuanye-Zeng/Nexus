"""rescore_listings tool — recompute match_score for all job_listings.

Run after the user updates their resume so existing listings re-rank
against the new profile sections. Idempotent.
"""
from __future__ import annotations

from typing import Any

from db import SessionLocal
from services.matching import rescore_all_listings

from .registry import register_tool


@register_tool("rescore_listings")
async def rescore_listings(args: dict[str, Any]) -> dict[str, Any]:
    """Recompute match_score over every listing against the active profile.

    No args. Returns: {updated: int}.
    """
    async with SessionLocal() as s:
        n = await rescore_all_listings(s)
    return {"updated": n}
