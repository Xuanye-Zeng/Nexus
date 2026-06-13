"""Query job_listings from the CLI.

The thing that turns Nexus into a daily-use tool: ranked listings filtered
to sponsor-friendly + match-relevant for international students.

Sensible defaults for Alex:
  - sponsorship_status IN ('sponsors', 'unclear')  (hide explicit denials)
  - sponsorship_confidence >= 0.0 (no floor)
  - ranked by match_score DESC, then sponsorship_confidence DESC

Run from backend/:
    venv/bin/python -m scripts.query_jobs                              # defaults
    venv/bin/python -m scripts.query_jobs --sponsors-only              # sponsors only
    venv/bin/python -m scripts.query_jobs --location Seattle --limit 30
    venv/bin/python -m scripts.query_jobs --min-score 0.5 --min-conf 0.7
    venv/bin/python -m scripts.query_jobs --company Stripe
    venv/bin/python -m scripts.query_jobs --show-evidence              # include JD evidence quote
    venv/bin/python -m scripts.query_jobs --json                       # JSON output for piping
"""
from __future__ import annotations

import argparse
import asyncio
import json as jsonlib
import sys
from dataclasses import dataclass

from sqlalchemy import and_, or_, select

from db import SessionLocal
from models import JobListing


@dataclass
class Filters:
    sponsors_only: bool
    hide_denials: bool
    location: str | None
    company: str | None
    source: str | None
    keyword: str | None
    min_score: float | None
    min_confidence: float | None
    limit: int
    show_evidence: bool
    json_out: bool


def _build_query(f: Filters):
    stmt = select(JobListing)

    if f.sponsors_only:
        stmt = stmt.where(JobListing.sponsorship_status == "sponsors")
    elif f.hide_denials:
        # Default: hide explicit denials and citizen-only roles.
        stmt = stmt.where(
            or_(
                JobListing.sponsorship_status.is_(None),
                JobListing.sponsorship_status.not_in(
                    ("no_sponsorship", "us_citizen_only")
                ),
            )
        )

    if f.location:
        stmt = stmt.where(JobListing.location.ilike(f"%{f.location}%"))
    if f.company:
        stmt = stmt.where(JobListing.company.ilike(f"%{f.company}%"))
    if f.source:
        stmt = stmt.where(JobListing.source == f.source)
    if f.keyword:
        stmt = stmt.where(
            or_(
                JobListing.title.ilike(f"%{f.keyword}%"),
                JobListing.description_clean.ilike(f"%{f.keyword}%"),
            )
        )
    if f.min_score is not None:
        stmt = stmt.where(JobListing.match_score >= f.min_score)
    if f.min_confidence is not None:
        stmt = stmt.where(JobListing.sponsorship_confidence >= f.min_confidence)

    stmt = stmt.order_by(
        JobListing.match_score.desc().nulls_last(),
        JobListing.sponsorship_confidence.desc().nulls_last(),
    ).limit(f.limit)

    return stmt


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


async def main(f: Filters) -> int:
    async with SessionLocal() as s:
        rows = (await s.execute(_build_query(f))).scalars().all()

    if not rows:
        print("(no listings match filters)", file=sys.stderr)
        return 0

    if f.json_out:
        out = [
            {
                "id": str(r.id),
                "source": r.source,
                "company": r.company,
                "title": r.title,
                "location": r.location,
                "source_url": r.source_url,
                "match_score": r.match_score,
                "sponsorship_status": r.sponsorship_status,
                "sponsorship_confidence": r.sponsorship_confidence,
                "sponsorship_evidence": r.sponsorship_evidence,
                "h1b_lca_count_recent": r.h1b_lca_count_recent,
                "cpt_opt_friendly": r.cpt_opt_friendly,
            }
            for r in rows
        ]
        print(jsonlib.dumps(out, indent=2, default=str))
        return 0

    # Table output
    print(
        f"{'#':>3}  {'src':<10}  {'score':>5}  {'conf':>5}  "
        f"{'status':<15}  {'12mo':>5}  {'company':<24}  {'title':<55}  location"
    )
    print("-" * 160)
    for i, r in enumerate(rows, 1):
        ms = f"{r.match_score:.2f}" if r.match_score is not None else "  -"
        conf = f"{r.sponsorship_confidence:.2f}" if r.sponsorship_confidence is not None else "  -"
        lca = str(r.h1b_lca_count_recent) if r.h1b_lca_count_recent is not None else "-"
        print(
            f"{i:>3}  {r.source:<10}  {ms:>5}  {conf:>5}  "
            f"{(r.sponsorship_status or '-'):<15}  {lca:>5}  "
            f"{_truncate(r.company, 24):<24}  {_truncate(r.title, 55):<55}  "
            f"{_truncate(r.location, 28)}"
        )
        if f.show_evidence and r.sponsorship_evidence:
            print(f"     └─ evidence: {_truncate(r.sponsorship_evidence, 120)!r}")
        if f.show_evidence and r.source_url:
            print(f"     └─ url:      {r.source_url}")
    print(f"\n({len(rows)} listings)")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sponsors-only",
        action="store_true",
        help="Show only status=sponsors (default also includes unclear)",
    )
    p.add_argument(
        "--include-denials",
        action="store_true",
        help="Disable the default filter that hides no_sponsorship + us_citizen_only",
    )
    p.add_argument("--location")
    p.add_argument("--company")
    p.add_argument("--source", choices=["adzuna", "greenhouse", "lever"])
    p.add_argument("--keyword", help="Substring match against title/description")
    p.add_argument("--min-score", type=float, help="match_score >= this")
    p.add_argument("--min-conf", type=float, help="sponsorship_confidence >= this")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--show-evidence", action="store_true")
    p.add_argument("--json", action="store_true", dest="json_out", help="JSON output")
    ns = p.parse_args()

    sys.exit(
        asyncio.run(
            main(
                Filters(
                    sponsors_only=ns.sponsors_only,
                    hide_denials=not ns.include_denials,
                    location=ns.location,
                    company=ns.company,
                    source=ns.source,
                    keyword=ns.keyword,
                    min_score=ns.min_score,
                    min_confidence=ns.min_conf,
                    limit=ns.limit,
                    show_evidence=ns.show_evidence,
                    json_out=ns.json_out,
                )
            )
        )
    )
