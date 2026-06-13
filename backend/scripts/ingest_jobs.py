"""Unified M2 ingest orchestrator (replaces the source-specific ingest_adzuna.py).

Dispatches to any registered connector via --source. Adding a new source
needs zero changes here — just write a new `connectors/<name>.py` decorated
with @register_connector and it shows up in `--source` automatically.

Pipeline (per listing):
  1. Fetch via the chosen connector (Adzuna / Greenhouse / Lever / ...)
  2. Embed description (nomic-embed-text, 768d)
  3. Classify sponsorship signal from JD text (Groq llama-3.3-70b)
  4. LCA join: 3-layer employer brand-to-legal lookup
  5. Resolve final sponsorship_status (plan §6 6-rule matrix)
  6. Match score: top-K mean cosine vs active resume profile sections
  7. UPSERT into job_listings (idempotent on source+source_id)

Run from backend/:
    venv/bin/python -m scripts.ingest_jobs --source adzuna --keyword "software engineer" --location Seattle
    venv/bin/python -m scripts.ingest_jobs --source greenhouse --keyword intern --max 30
    venv/bin/python -m scripts.ingest_jobs --source lever --max 30
    venv/bin/python -m scripts.ingest_jobs --source adzuna --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from connectors import NormalizedListing, get_connector, list_connectors
from db import SessionLocal
from models import JobListing, PromptTemplate
from services.embedding import embed_text
from services.employer_lookup import lookup_employer
from services.llm import describe_profile, get_llm
from services.matching import score_listing_against_active_profile
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
                f"No active prompt template {SPONSORSHIP_PROMPT_NAME!r}."
            )
        return row.content


def _classify_jd(llm: BaseChatModel, prompt: str, jd_text: str) -> dict:
    resp = llm.invoke(
        [SystemMessage(content=prompt), HumanMessage(content=f"## JD\n{jd_text}")]
    )
    try:
        return parse_classifier_output(resp.content)
    except (ValueError, KeyError):
        return {
            "status": "unclear",
            "evidence": "",
            "cpt_opt_signal": False,
            "confidence": 0.0,
        }


async def _enrich(
    listing: NormalizedListing,
    llm: BaseChatModel,
    classifier_prompt: str,
) -> dict:
    """Run the full enrichment chain on one listing. Returns dict ready to UPSERT."""
    jd_text = listing.description_raw or ""

    if not jd_text.strip():
        verdict = SponsorshipVerdict(
            status="unclear",
            confidence=0.0,
            evidence="",
            cpt_opt_friendly=False,
            h1b_lca_count_recent=None,
            h1b_lca_year=None,
            reasoning="no description text from connector",
        )
        return _to_row(listing, verdict, None, None, "miss")

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

        embedding = embed_text(jd_text[:8000])
        match_score = await score_listing_against_active_profile(s, embedding)

    return _to_row(listing, verdict, embedding, match_score, match_layer)


def _to_row(
    listing: NormalizedListing,
    verdict: SponsorshipVerdict,
    embedding: list[float] | None,
    match_score: float | None,
    match_layer: str,
) -> dict:
    return {
        "_match_layer": match_layer,  # stripped before insert; for logging only
        "source": listing.source,
        "source_id": listing.source_id,
        "source_url": listing.source_url,
        "company": listing.company,
        "title": listing.title,
        "location": listing.location,
        "description_raw": listing.description_raw,
        "description_clean": listing.description_raw,
        "scraped_at": listing.scraped_at,
        "embedding": embedding,
        "match_score": match_score,
        "sponsorship_status": verdict.status,
        "sponsorship_evidence": verdict.evidence or None,
        "sponsorship_confidence": verdict.confidence,
        "h1b_lca_count_recent": verdict.h1b_lca_count_recent,
        "h1b_lca_year": verdict.h1b_lca_year,
        "cpt_opt_friendly": verdict.cpt_opt_friendly,
        "_verdict": verdict,  # stripped before insert; for logging
    }


async def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [
        {k: v for k, v in r.items() if not k.startswith("_")} for r in rows
    ]
    async with SessionLocal() as s:
        stmt = pg_insert(JobListing).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "source_id"],
            set_={
                c: getattr(stmt.excluded, c)
                for c in (
                    "title", "location", "description_raw", "description_clean",
                    "scraped_at", "embedding", "match_score",
                    "sponsorship_status", "sponsorship_evidence",
                    "sponsorship_confidence", "h1b_lca_count_recent",
                    "h1b_lca_year", "cpt_opt_friendly",
                )
            },
        )
        await s.execute(stmt)
        await s.commit()
    return len(payload)


async def main(
    source: str,
    keyword: str | None,
    location: str | None,
    max_results: int,
    dry_run: bool,
) -> int:
    try:
        connector = get_connector(source)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    classifier_prompt = await _fetch_classifier_prompt()
    llm = get_llm("sponsorship_classifier")

    print(
        f"sponsorship_classifier LLM: {describe_profile('sponsorship_classifier')}"
    )
    print(f"Fetching via {source} connector (keyword={keyword!r} location={location!r} max={max_results})...")
    listings = await connector.fetch(
        keyword=keyword, location=location, max_results=max_results
    )
    print(f"  fetched {len(listings)} listings\n")

    if not listings:
        print("No listings to ingest.")
        return 0

    print(f"Enriching: sponsorship classify -> LCA join -> embed -> match-score -> UPSERT\n")
    print(
        f"  {'#':>3}  {'company':<25}  {'status':<16}  {'conf':<5}  "
        f"{'12mo':>5}  {'match':<6}  {'score':<5}  reasoning"
    )
    print("  " + "-" * 130)

    rows: list[dict] = []
    for i, lst in enumerate(listings, 1):
        row = await _enrich(lst, llm, classifier_prompt)
        rows.append(row)
        verdict: SponsorshipVerdict = row["_verdict"]
        layer = row["_match_layer"]
        ms = row["match_score"]
        print(
            f"  {i:>3}  {lst.company[:25]:<25}  {verdict.status:<16}  "
            f"{verdict.confidence:<5.2f}  "
            f"{str(verdict.h1b_lca_count_recent or '-'):>5}  "
            f"{layer:<6}  "
            f"{f'{ms:.2f}' if ms is not None else '-':<5}  "
            f"{verdict.reasoning[:55]}"
        )

    by_status: dict[str, int] = {}
    by_match: dict[str, int] = {}
    for r in rows:
        v = r["_verdict"]
        by_status[v.status] = by_status.get(v.status, 0) + 1
        by_match[r["_match_layer"]] = by_match.get(r["_match_layer"], 0) + 1
    print(f"\nstatus breakdown: {by_status}")
    print(f"LCA-match layers: {by_match}")

    if dry_run:
        print("\n(dry-run: no DB writes)")
        return 0

    print(f"\nUPSERTing {len(rows)} listings into job_listings...")
    n = await _upsert(rows)
    print(f"  done: {n} committed")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        choices=list_connectors(),
        default="adzuna",
        help=f"Connector to use. Available: {', '.join(list_connectors())}",
    )
    p.add_argument("--keyword", default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--max", type=int, default=20, help="Max listings to ingest")
    p.add_argument("--dry-run", action="store_true")
    ns = p.parse_args()
    sys.exit(asyncio.run(main(ns.source, ns.keyword, ns.location, ns.max, ns.dry_run)))
