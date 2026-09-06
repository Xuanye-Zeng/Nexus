"""Manual probe for the Adzuna connector. Fetches US software-engineering
listings and prints a compact summary. Does NOT touch the DB.

Run from backend/:  venv/bin/python -m scripts.probe_adzuna
                    venv/bin/python -m scripts.probe_adzuna --keyword "machine learning" --location Seattle
"""
import argparse
import asyncio

from connectors.adzuna import AdzunaConnector


async def main(keyword: str, location: str | None, max_results: int) -> None:
    print(f"Fetching Adzuna listings for keyword={keyword!r} location={location!r}...")
    listings = await AdzunaConnector().fetch(
        keyword=keyword,
        location=location,
        max_results=max_results,
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
    p.add_argument("--max-results", type=int, default=10)
    ns = p.parse_args()
    asyncio.run(main(ns.keyword, ns.location, ns.max_results))
