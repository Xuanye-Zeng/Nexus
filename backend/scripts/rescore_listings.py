"""Recompute job_listings.match_score against the current active resume profile.

Run this after `scripts/seed_resume.py` updates the resume so previously-
ingested listings re-rank against the new profile sections.

Run from backend/:  venv/bin/python -m scripts.rescore_listings
"""
import asyncio
import sys

from db import SessionLocal
from services.matching import rescore_all_listings


async def main() -> int:
    async with SessionLocal() as s:
        n = await rescore_all_listings(s)
    print(f"rescored {n} listings against active profile.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
