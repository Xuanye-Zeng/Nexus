"""Single source of truth for the M2 ingest pipeline.

Shape:
    fetch via a connector
    -> per-listing enrich
        ├── sponsorship_classifier LLM call
        ├── employer LCA lookup
        ├── resolve_sponsorship (§6 6-rule matrix)
        ├── nomic-embed-text embedding
        └── top-K match score vs active profile
    -> idempotent UPSERT into job_listings on (source, source_id)

Used by:
    scripts/ingest_jobs.py     (CLI)
    tools/ingest_jobs.py       (Master Agent tool)
    tasks.py                   (Celery 6h beat — via scripts/ingest_jobs.main)

Before this module existed, the enrichment + upsert logic was duplicated
across the CLI script and the agent tool. Single source means future
changes (e.g. swapping the sponsorship_classifier model, adjusting the LCA
lookup layers) land in one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from connectors import NormalizedListing, get_connector
from db import SessionLocal
from models import JobListing, PromptTemplate
from services.embedding import aembed_text
from services.employer_lookup import lookup_employer
from services.llm import get_llm
from services.matching import score_listing_against_active_profile
from services.sponsorship import (
    SponsorshipVerdict,
    parse_classifier_output,
    resolve_sponsorship,
)

SPONSORSHIP_PROMPT_NAME = "sponsorship_classifier"


@dataclass
class EnrichedListing:
    """One UPSERT-ready row + the debug metadata (match layer, verdict)."""
    row: dict[str, Any]
    verdict: SponsorshipVerdict
    match_layer: str  # 'alias' | 'exact' | 'prefix' | 'reverse_prefix' | 'miss'


@dataclass
class IngestStats:
    fetched: int
    committed: int
    by_status: dict[str, int]
    by_match_layer: dict[str, int]
    sample: list[dict[str, Any]]


# ---------- shared helpers ----------


async def fetch_classifier_prompt() -> str:
    """Resolve the active sponsorship_classifier prompt content."""
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
    """Best-effort sponsorship classification. Falls back to 'unclear' on
    any parse / LLM error so the surrounding pipeline still produces a row."""
    try:
        resp = llm.invoke(
            [SystemMessage(content=prompt), HumanMessage(content=f"## JD\n{jd_text}")]
        )
        return parse_classifier_output(resp.content)
    except Exception:  # noqa: BLE001 — classify failure must not poison the batch
        return {
            "status": "unclear",
            "evidence": "",
            "cpt_opt_signal": False,
            "confidence": 0.0,
        }


def _row_from(
    listing: NormalizedListing,
    verdict: SponsorshipVerdict,
    embedding: list[float] | None,
    match_score: float | None,
) -> dict[str, Any]:
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


# ---------- per-listing pipeline ----------


async def enrich_listing(
    listing: NormalizedListing,
    llm: BaseChatModel,
    classifier_prompt: str,
) -> EnrichedListing:
    """Run the full sponsorship + LCA + embed + match pipeline on one listing.

    Listings without a description body still produce an `unclear` row so the
    UPSERT is consistent — downstream the user can filter on confidence > 0.05.
    """
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
        return EnrichedListing(
            row=_row_from(listing, verdict, None, None),
            verdict=verdict,
            match_layer="miss",
        )

    cls = _classify_jd(llm, classifier_prompt, jd_text)

    async with SessionLocal() as s:
        emp_row, match_layer = await lookup_employer(s, listing.company)
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

        embedding = await aembed_text(jd_text[:8000])
        match_score = await score_listing_against_active_profile(s, embedding)

    return EnrichedListing(
        row=_row_from(listing, verdict, embedding, match_score),
        verdict=verdict,
        match_layer=match_layer,
    )


# ---------- upsert ----------


_UPSERT_UPDATE_COLS = (
    "title", "location", "description_raw", "description_clean",
    "scraped_at", "embedding", "match_score",
    "sponsorship_status", "sponsorship_evidence",
    "sponsorship_confidence", "h1b_lca_count_recent",
    "h1b_lca_year", "cpt_opt_friendly",
)


async def upsert_rows(rows: list[dict[str, Any]]) -> int:
    """Idempotent UPSERT on (source, source_id). Returns rows touched."""
    if not rows:
        return 0
    async with SessionLocal() as s:
        stmt = pg_insert(JobListing).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "source_id"],
            set_={c: getattr(stmt.excluded, c) for c in _UPSERT_UPDATE_COLS},
        )
        await s.execute(stmt)
        await s.commit()
    return len(rows)


# ---------- top-level orchestrator ----------


async def ingest_from_source(
    source: str,
    keyword: str | None = None,
    location: str | None = None,
    max_results: int = 20,
    *,
    dry_run: bool = False,
    progress: Any | None = None,  # callable (i, total, enriched) -> None
) -> IngestStats:
    """Fetch via a connector, enrich each listing, UPSERT (unless dry_run).
    `progress` callable is invoked once per enriched listing so callers can
    stream a status line during long runs.
    """
    connector = get_connector(source)
    listings = await connector.fetch(
        keyword=keyword, location=location, max_results=max_results
    )

    if not listings:
        return IngestStats(
            fetched=0, committed=0, by_status={}, by_match_layer={}, sample=[]
        )

    classifier_prompt = await fetch_classifier_prompt()
    llm = get_llm("sponsorship_classifier")

    enriched: list[EnrichedListing] = []
    for i, lst in enumerate(listings, 1):
        e = await enrich_listing(lst, llm, classifier_prompt)
        enriched.append(e)
        if progress is not None:
            try:
                progress(i, len(listings), e)
            except Exception:  # noqa: BLE001 — progress is observational only
                pass

    by_status: dict[str, int] = {}
    by_match: dict[str, int] = {}
    for e in enriched:
        by_status[e.verdict.status] = by_status.get(e.verdict.status, 0) + 1
        by_match[e.match_layer] = by_match.get(e.match_layer, 0) + 1

    sample = [
        {
            "company": e.row["company"],
            "title": e.row["title"],
            "sponsorship_status": e.row["sponsorship_status"],
            "h1b_lca_count_recent": e.row["h1b_lca_count_recent"],
            "match_score": e.row["match_score"],
        }
        for e in enriched[:5]
    ]

    committed = 0
    if not dry_run:
        committed = await upsert_rows([e.row for e in enriched])

    return IngestStats(
        fetched=len(listings),
        committed=committed,
        by_status=by_status,
        by_match_layer=by_match,
        sample=sample,
    )
