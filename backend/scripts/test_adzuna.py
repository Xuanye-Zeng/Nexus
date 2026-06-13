"""Smoke test for Adzuna connector. Fetches one page of US software-engineering
listings and prints a compact summary. Does NOT touch the DB.

Run from backend/:  venv/bin/python -m scripts.test_adzuna
                    venv/bin/python -m scripts.test_adzuna --keyword "machine learning" --location Seattle
"""
import argparse
import asyncio

from connectors.adzuna import fetch_listings


async def main(keyword: str, location: str | None, page: int) -> None:
    print(f"Fetching Adzuna page {page} for keyword={keyword!r} location={location!r}...")
    listings = await fetch_listings(
        keyword=keyword,
        location=location,
        page=page,
        results_per_page=10,
    )
    print(f"Got {len(listings)} listings.\n")

    for i, lst in enumerate(listings, 1):
        desc_preview = (lst.description_raw or "")[:80].replace("\n", " ")
        print(f"[{i:>2}] {lst.company[:35]:<35} | {lst.title[:50]:<50}")
        print(f"     loc: {lst.location or '(none)':<50} url: {lst.source_url}")
        print(f"     scraped_at: {lst.scraped_at}  desc: {desc_preview}...")
        print()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keyword", default="software engineer")
    p.add_argument("--location", default=None)
    p.add_argument("--page", type=int, default=1)
    ns = p.parse_args()
    asyncio.run(main(ns.keyword, ns.location, ns.page))
