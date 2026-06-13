"""Parse DOL OFLC LCA Disclosure Data xlsx file(s) and aggregate into h1b_employers.

Each row = one LCA application. Columns include CASE_STATUS, VISA_CLASS,
DECISION_DATE, JOB_TITLE, EMPLOYER_NAME, ...

Aggregation: (employer_name_normalized) -> {count_total, count_last_12mo,
most_recent_filing_year, most_recent_filing_date, top_job_titles}, filtering:
  - CASE_STATUS == 'Certified'  (drop withdrawn/denied)
  - VISA_CLASS in H-1B family   (drop H-2A/H-2B agricultural/non-specialty)

Multi-file: when --dir is supplied (default `data/dol_lca/`), all *.xlsx files
in the dir are concatenated and aggregated together. The 12-month window is
anchored at the GLOBAL max decision_date across all files, so feeding multiple
fiscal years yields a coherent rolling-12mo count.

UPSERT into h1b_employers keyed on employer_name_normalized.

Run from backend/:
    venv/bin/python -m scripts.ingest_dol_lca --dry-run
    venv/bin/python -m scripts.ingest_dol_lca               # write to DB
    venv/bin/python -m scripts.ingest_dol_lca --file data/dol_lca/single.xlsx
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db import SessionLocal
from models import H1BEmployer
from services.normalize import normalize_company_name

RELEVANT_VISA_CLASSES = {
    "H-1B",
    "H-1B1 Chile",
    "H-1B1 Singapore",
    "E-3 Australian",
}

COLUMN_ALIASES = {
    "case_status": ["CASE_STATUS", "Case Status", "STATUS"],
    "visa_class": ["VISA_CLASS", "Visa Class"],
    "decision_date": ["DECISION_DATE", "Decision Date"],
    "employer_name": ["EMPLOYER_NAME", "Employer Name"],
    "job_title": ["JOB_TITLE", "Job Title"],
}


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map logical column names to actual DataFrame column names."""
    resolved: dict[str, str] = {}
    for logical, candidates in COLUMN_ALIASES.items():
        match = next((c for c in candidates if c in df.columns), None)
        if match is None:
            raise KeyError(
                f"Could not find a column for {logical!r}. "
                f"Tried {candidates}. Available: {list(df.columns)[:20]}..."
            )
        resolved[logical] = match
    return resolved


def _load_and_filter(file: Path) -> pd.DataFrame:
    """Load one xlsx, filter to Certified + H-1B family, return a small DataFrame
    with normalized logical column names (case_status / visa_class / ...).
    """
    print(f"  loading {file.name} ({file.stat().st_size / 1024 / 1024:.0f}MB)...", end="", flush=True)
    df = pd.read_excel(file, engine="openpyxl")
    cols = _resolve_columns(df)

    df = df[
        (df[cols["case_status"]] == "Certified")
        & (df[cols["visa_class"]].isin(RELEVANT_VISA_CLASSES))
    ][[cols["decision_date"], cols["employer_name"], cols["job_title"]]].copy()

    df.columns = ["decision_date", "employer_name", "job_title"]
    df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
    df = df.dropna(subset=["decision_date", "employer_name"])
    print(f" {len(df):,} certified H-1B rows")
    return df


def _aggregate(df: pd.DataFrame) -> dict[str, dict]:
    """Aggregate filtered+concatenated DataFrame into employer-level rows."""
    if df.empty:
        return {}

    # Global max date anchors the rolling 12mo window.
    max_decision = df["decision_date"].max()
    window_start = max_decision - pd.Timedelta(days=365)
    print(
        f"\nMax decision_date across all files: {max_decision.date()}; "
        f"rolling-12mo window starts {window_start.date()}"
    )

    df["_normalized"] = df["employer_name"].astype(str).apply(normalize_company_name)
    df = df[df["_normalized"] != ""]

    out: dict[str, dict] = {}
    for normalized, group in df.groupby("_normalized", sort=False):
        display = group["employer_name"].mode().iat[0]
        count_total = int(len(group))
        count_last_12mo = int((group["decision_date"] >= window_start).sum())
        max_date: datetime = group["decision_date"].max().to_pydatetime()
        titles = group["job_title"].dropna().astype(str).str.strip()
        top_titles = [t for t, _ in Counter(titles).most_common(5)]

        out[normalized] = {
            "employer_name_normalized": normalized,
            "employer_name_display": display,
            "lca_count_total": count_total,
            "lca_count_last_12mo": count_last_12mo,
            "most_recent_filing_year": int(max_date.year),
            "most_recent_filing_date": max_date.date(),
            "top_job_titles": top_titles,
        }
    return out


async def _upsert(rows: list[dict]) -> int:
    if not rows:
        return 0
    async with SessionLocal() as s:
        # Batch UPSERT in chunks to avoid huge parameter lists.
        CHUNK = 1000
        total = 0
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i : i + CHUNK]
            stmt = pg_insert(H1BEmployer).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["employer_name_normalized"],
                set_={
                    "employer_name_display": stmt.excluded.employer_name_display,
                    "lca_count_total": stmt.excluded.lca_count_total,
                    "lca_count_last_12mo": stmt.excluded.lca_count_last_12mo,
                    "most_recent_filing_year": stmt.excluded.most_recent_filing_year,
                    "most_recent_filing_date": stmt.excluded.most_recent_filing_date,
                    "top_job_titles": stmt.excluded.top_job_titles,
                },
            )
            await s.execute(stmt)
            total += len(chunk)
        await s.commit()
    return total


def _resolve_files(file: Path | None, dir_: Path) -> list[Path]:
    if file:
        return [file]
    return sorted(dir_.glob("*.xlsx"))


async def main(file: Path | None, dir_: Path, dry_run: bool, preview: int) -> int:
    files = _resolve_files(file, dir_)
    if not files:
        print(f"ERROR: no .xlsx in {dir_}", file=sys.stderr)
        return 2

    print(f"Files to ingest ({len(files)}):")
    for f in files:
        if not f.exists():
            print(f"  MISSING: {f}", file=sys.stderr)
            return 2
        print(f"  - {f.name}")
    print()

    frames: list[pd.DataFrame] = []
    for f in files:
        frames.append(_load_and_filter(f))

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nCombined: {len(combined):,} certified H-1B family rows across {len(files)} file(s)")

    print("\nAggregating by normalized employer name...")
    aggregates = _aggregate(combined)
    print(f"  -> {len(aggregates):,} unique normalized employers")

    if not aggregates:
        print("WARNING: no rows survived filtering.", file=sys.stderr)
        return 3

    sorted_employers = sorted(
        aggregates.values(),
        key=lambda r: (r["lca_count_last_12mo"], r["lca_count_total"]),
        reverse=True,
    )

    print(f"\nTop {preview} employers by LCA filings in last 12 months:")
    print(f"  {'rank':>4}  {'12mo':>7}  {'total':>7}  most_recent  legal name")
    print("  " + "-" * 100)
    for i, r in enumerate(sorted_employers[:preview], 1):
        print(
            f"  {i:>4}  {r['lca_count_last_12mo']:>7,}  {r['lca_count_total']:>7,}  "
            f"{r['most_recent_filing_date']}  {r['employer_name_display'][:65]}"
        )

    if dry_run:
        print("\n(dry-run: no DB writes)")
        return 0

    print(f"\nUPSERTing {len(aggregates):,} rows into h1b_employers...")
    n = await _upsert(list(aggregates.values()))
    print(f"  done: {n:,} rows committed")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", type=Path, default=None, help="Single xlsx (overrides --dir)")
    p.add_argument(
        "--dir",
        type=Path,
        default=Path("data/dol_lca"),
        help="Directory to glob *.xlsx from (default: data/dol_lca/)",
    )
    p.add_argument("--dry-run", action="store_true", help="Parse + preview without DB writes")
    p.add_argument("--preview", type=int, default=50, help="How many top employers to print")
    ns = p.parse_args()
    sys.exit(asyncio.run(main(ns.file, ns.dir, ns.dry_run, ns.preview)))
