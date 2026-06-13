"""End-to-end M2 ingest pipeline.

For each Adzuna search result:
  1. Fetch via Adzuna API
  2. Embed description (nomic-embed-text)
  3. Classify sponsorship from JD text (Groq llama-3.3-70b)
  4. Look up employer in h1b_employers (3-layer brand-to-legal match)
  5. Resolve final sponsorship_status via plan §6 logic
  6. UPSERT into job_listings (idempotent on source+source_id)

Run from backend/:
    venv/bin/python -m scripts.ingest_adzuna --keyword "software engineer intern" --location Seattle --pages 1
    venv/bin/python -m scripts.ingest_adzuna --dry-run   # no DB writes
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from connectors.adzuna import AdzunaListing, fetch_listings
from db import SessionLocal
from models import JobListing, PromptTemplate
from services.embedding import embed_text
from services.employer_lookup import lookup_employer
from services.sponsorship import (
    SponsorshipVerdict,
    parse_classifier_output,
    resolve_sponsorship,
)

SPONSORSHIP_PROMPT_NAME = "sponsorship_classifier"


async def _fetch_classifier_prompt() -> str:
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == SPONSORSHIP_PROMPT_NAME,
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RuntimeError(
                f"No active prompt template {SPONSORSHIP_PROMPT_NAME!r}. "
                "Did you run scripts/seed_prompts.py?"
            )
        return row.content


def _classify_jd(llm: ChatGroq, prompt: str, jd_text: str) -> dict:
    """Run the sponsorship_classifier LLM. Returns parsed JSON or a fallback dict."""
    resp = llm.invoke(
        [SystemMessage(content=prompt), HumanMessage(content=f"## JD\n{jd_text}")]
    )
    try:
        return parse_classifier_output(resp.content)
    except (ValueError, KeyError) as e:
        return {
            "status": "unclear",
            "evidence": "",
            "cpt_opt_signal": False,
            "confidence": 0.0,
            "_parse_error": str(e),
            "_raw": resp.content[:200],
        }


async def _process(
    listing: AdzunaListing,
    llm: ChatGroq,
    classifier_prompt: str,
) -> tuple[AdzunaListing, SponsorshipVerdict, str, list[float] | None]:
    """Run all enrichment steps for one listing. Returns (listing, verdict, match_layer, embedding)."""
    jd_text = listing.description_raw or ""
    if not jd_text.strip():
        # No description text — can't classify or embed meaningfully.
        verdict = SponsorshipVerdict(
            status="unclear",
            confidence=0.0,
            evidence="",
            cpt_opt_friendly=False,
            h1b_lca_count_recent=None,
            h1b_lca_year=None,
            reasoning="no description text from Adzuna",
        )
        return listing, verdict, "miss", None

    classifier_out = _classify_jd(llm, classifier_prompt, jd_text)

    async with SessionLocal() as s:
        emp_row, match_layer = await lookup_employer(s, listing.company)

    lca_count = emp_row.lca_count_last_12mo if emp_row else None
    lca_year = emp_row.most_recent_filing_year if emp_row else None

    verdict = resolve_sponsorship(
        jd_status=classifier_out.get("status", "unclear"),
        jd_confidence=float(classifier_out.get("confidence", 0.0)),
        jd_evidence=classifier_out.get("evidence", "") or "",
        cpt_opt_signal=bool(classifier_out.get("cpt_opt_signal", False)),
        lca_count_12mo=lca_count,
        lca_most_recent_year=lca_year,
    )

    embedding = embed_text(jd_text[:8000])  # cap to keep Ollama fast on long JDs

    return listing, verdict, match_layer, embedding


async def _upsert_listings(
    rows: list[
        tuple[AdzunaListing, SponsorshipVerdict, str, list[float] | None]
    ]
) -> int:
    if not rows:
        return 0
    payload = []
    for listing, verdict, _layer, embedding in rows:
        payload.append(
            {
                "source": listing.source,
                "source_id": listing.source_id,
                "source_url": listing.source_url,
                "company": listing.company,
                "title": listing.title,
                "location": listing.location,
                "description_raw": listing.description_raw,
                "description_clean": listing.description_raw,  # TODO: HTML strip if needed
                "scraped_at": listing.scraped_at,
                "embedding": embedding,
                "sponsorship_status": verdict.status,
                "sponsorship_evidence": verdict.evidence or None,
                "sponsorship_confidence": verdict.confidence,
                "h1b_lca_count_recent": verdict.h1b_lca_count_recent,
                "h1b_lca_year": verdict.h1b_lca_year,
                "cpt_opt_friendly": verdict.cpt_opt_friendly,
            }
        )
    async with SessionLocal() as s:
        stmt = pg_insert(JobListing).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "source_id"],
            set_={
                "title": stmt.excluded.title,
                "location": stmt.excluded.location,
                "description_raw": stmt.excluded.description_raw,
                "description_clean": stmt.excluded.description_clean,
                "scraped_at": stmt.excluded.scraped_at,
                "embedding": stmt.excluded.embedding,
                "sponsorship_status": stmt.excluded.sponsorship_status,
                "sponsorship_evidence": stmt.excluded.sponsorship_evidence,
                "sponsorship_confidence": stmt.excluded.sponsorship_confidence,
                "h1b_lca_count_recent": stmt.excluded.h1b_lca_count_recent,
                "h1b_lca_year": stmt.excluded.h1b_lca_year,
                "cpt_opt_friendly": stmt.excluded.cpt_opt_friendly,
            },
        )
        await s.execute(stmt)
        await s.commit()
    return len(payload)


async def main(keyword: str, location: str | None, pages: int, dry_run: bool) -> int:
    classifier_prompt = await _fetch_classifier_prompt()
    llm = ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY.get_secret_value(),
    )

    all_listings: list[AdzunaListing] = []
    for page in range(1, pages + 1):
        page_results = await fetch_listings(
            keyword=keyword, location=location, page=page, results_per_page=10
        )
        if not page_results:
            print(f"page {page}: empty, stopping pagination")
            break
        print(f"page {page}: {len(page_results)} listings")
        all_listings.extend(page_results)

    if not all_listings:
        print("no listings fetched.", file=sys.stderr)
        return 1

    print(f"\nEnriching {len(all_listings)} listings (sponsorship + embed + LCA join)...\n")
    print(
        f"  {'#':>3}  {'company':<28}  {'status':<16}  {'conf':<5}  "
        f"{'cpt':<3}  {'12mo':>5}  {'match':<6}  reasoning"
    )
    print("  " + "-" * 130)

    processed = []
    for i, lst in enumerate(all_listings, 1):
        result = await _process(lst, llm, classifier_prompt)
        _, verdict, match_layer, _ = result
        processed.append(result)

        print(
            f"  {i:>3}  {lst.company[:28]:<28}  {verdict.status:<16}  "
            f"{verdict.confidence:<5.2f}  "
            f"{'Y' if verdict.cpt_opt_friendly else '-':<3}  "
            f"{str(verdict.h1b_lca_count_recent or '-'):>5}  "
            f"{match_layer:<6}  {verdict.reasoning[:55]}"
        )

    # Summary by status
    by_status: dict[str, int] = {}
    by_match: dict[str, int] = {}
    for _, v, layer, _ in processed:
        by_status[v.status] = by_status.get(v.status, 0) + 1
        by_match[layer] = by_match.get(layer, 0) + 1
    print(f"\nstatus breakdown: {by_status}")
    print(f"LCA-match layers: {by_match}")

    if dry_run:
        print("\n(dry-run: no DB writes)")
        return 0

    print(f"\nUPSERTing {len(processed)} listings into job_listings...")
    n = await _upsert_listings(processed)
    print(f"  done: {n} listings committed")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keyword", default="software engineer")
    p.add_argument("--location", default=None)
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    ns = p.parse_args()
    sys.exit(asyncio.run(main(ns.keyword, ns.location, ns.pages, ns.dry_run)))
