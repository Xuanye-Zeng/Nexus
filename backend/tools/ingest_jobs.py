"""ingest_jobs tool — trigger source ingest from the agent.

Wraps the full M2 pipeline (fetch -> classify sponsorship -> embed -> LCA
join -> resolve -> UPSERT) the same way scripts/ingest_jobs.py does, but
callable from the Master Agent in response to a user request like
"pull more Stripe backend jobs" or "get me 30 more Anthropic listings".
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from connectors import NormalizedListing, get_connector, list_connectors
from db import SessionLocal
from models import JobListing, PromptTemplate
from services.embedding import embed_text
from services.employer_lookup import lookup_employer
from services.llm import get_llm
from services.matching import score_listing_against_active_profile
from services.sponsorship import (
    SponsorshipVerdict,
    parse_classifier_output,
    resolve_sponsorship,
)

from .registry import register_tool

DEFAULT_MAX = 15  # cap agent-triggered ingests to keep latency reasonable


async def _fetch_classifier_prompt() -> str:
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == "sponsorship_classifier",
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            )
        ).scalar_one()
        return row.content


async def _enrich_one(
    listing: NormalizedListing, llm, classifier_prompt: str
) -> dict:
    jd_text = listing.description_raw or ""
    if not jd_text.strip():
        verdict = SponsorshipVerdict(
            status="unclear", confidence=0.0, evidence="",
            cpt_opt_friendly=False, h1b_lca_count_recent=None,
            h1b_lca_year=None, reasoning="no description from connector",
        )
        embedding = None
        match_score = None
    else:
        resp = llm.invoke(
            [SystemMessage(content=classifier_prompt), HumanMessage(content=f"## JD\n{jd_text}")]
        )
        try:
            cls = parse_classifier_output(resp.content)
        except Exception:
            cls = {"status": "unclear", "evidence": "", "cpt_opt_signal": False, "confidence": 0.0}

        async with SessionLocal() as s:
            emp_row, _layer = await lookup_employer(s, listing.company)
            lca_count = emp_row.lca_count_last_12mo if emp_row else None
            lca_year = emp_row.most_recent_filing_year if emp_row else None

            verdict = resolve_sponsorship(
                jd_status=cls.get("status", "unclear"),
                jd_confidence=float(cls.get("confidence", 0.0)),
                jd_evidence=cls.get("evidence", "") or "",
                cpt_opt_signal=bool(cls.get("cpt_opt_signal", False)),
                lca_count_12mo=lca_count,
                lca_most_recent_year=lca_year,
            )
            embedding = embed_text(jd_text[:8000])
            match_score = await score_listing_against_active_profile(s, embedding)

    return {
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
    }


async def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    async with SessionLocal() as s:
        stmt = pg_insert(JobListing).values(rows)
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
    return len(rows)


@register_tool("ingest_jobs")
async def ingest_jobs(args: dict[str, Any]) -> dict[str, Any]:
    """Pull fresh listings from a connector + enrich + UPSERT.

    Args:
      source (str, required): one of {adzuna, greenhouse, lever, ...}.
      keyword (str, optional): query keyword.
      location (str, optional): location filter (Adzuna only honors this natively).
      max (int, optional, default 15, capped at DEFAULT_MAX): how many to pull.

    Returns: {source, fetched, committed, status_breakdown, sample}.
    """
    source = (args.get("source") or "").strip().lower()
    if not source:
        return {"error": f"ingest_jobs requires `source`. Available: {list_connectors()}"}
    try:
        connector = get_connector(source)
    except KeyError as e:
        return {"error": str(e)}

    max_results = min(int(args.get("max", DEFAULT_MAX)), DEFAULT_MAX)
    keyword = args.get("keyword")
    location = args.get("location")

    listings = await connector.fetch(
        keyword=keyword, location=location, max_results=max_results
    )
    if not listings:
        return {"source": source, "fetched": 0, "committed": 0, "message": "no listings returned"}

    classifier_prompt = await _fetch_classifier_prompt()
    llm = get_llm("sponsorship_classifier")

    rows = []
    for lst in listings:
        rows.append(await _enrich_one(lst, llm, classifier_prompt))

    committed = await _upsert(rows)

    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["sponsorship_status"]] = by_status.get(r["sponsorship_status"], 0) + 1

    sample = [
        {
            "company": r["company"],
            "title": r["title"],
            "sponsorship_status": r["sponsorship_status"],
            "h1b_lca_count_recent": r["h1b_lca_count_recent"],
        }
        for r in rows[:5]
    ]

    return {
        "source": source,
        "fetched": len(listings),
        "committed": committed,
        "filters": {k: v for k, v in {"keyword": keyword, "location": location, "max": max_results}.items() if v},
        "status_breakdown": by_status,
        "sample": sample,
    }
