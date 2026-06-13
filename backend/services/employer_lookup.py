"""Match an Adzuna-style company name to the H-1B LCA filer in h1b_employers.

The mismatch problem: Adzuna lists "Amazon" / "Meta" / "Walmart" while LCA
filings use legal entity names like "Amazon.com Services LLC" / "Meta
Platforms, Inc" / "Wal-Mart Associates, Inc.". After normalize_company_name,
these still don't match by equality.

Resolution layers (tried in order, first hit wins):
  1. ALIAS — hand-curated mapping for brands where legal != trading name.
     Tried FIRST so that "amazon" resolves to "amazon com services" (8K
     LCAs/yr) rather than colliding with some incidental "Amazon LLC"
     (2 LCAs) that also normalizes to "amazon".
  2. EXACT — normalized equality (catches Apple Inc. / Google LLC /
     Stripe Inc. — brand == legal once suffixes are stripped).
  3. PREFIX_TOKEN — Adzuna name is a complete-word prefix of the LCA name
     ("anthropic" matches "anthropic pbc", "oracle" matches "oracle
     america"). Picks the candidate with the most LCAs in the last 12mo.

Returns None if all three layers miss — the caller should fall back to the
JD-text sponsorship_classifier signal alone.

Alias-target values are the ACTUAL normalized strings present in
h1b_employers.employer_name_normalized — verified against the DB after
each LCA ingest. Update them when DOL changes employer-name formatting.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import H1BEmployer
from services.normalize import normalize_company_name

# Adzuna-brand (normalized) -> target row's employer_name_normalized.
# Values must match the DB exactly (verified post-ingest).
EMPLOYER_ALIASES: dict[str, str] = {
    # Big Tech
    "meta": "meta platforms",
    "facebook": "meta platforms",
    "amazon": "amazon com services",
    "aws": "amazon web services",
    "amazon web services": "amazon web services",
    "google": "google",
    "alphabet": "google",
    "tiktok": "tiktok",
    "bytedance": "bytedance",

    # Big retail
    "walmart": "wal mart associates",
    "wal mart": "wal mart associates",

    # Big finance — note "&" stays after normalization
    "jpmorgan": "jpmorgan chase &",
    "jpmorgan chase": "jpmorgan chase &",
    "jpmc": "jpmorgan chase &",
    "chase": "jpmorgan chase &",
    "capital one": "capital one services",
    "goldman sachs": "goldman sachs &",
    "morgan stanley": "morgan stanley services",
    "citi": "citibank n a",
    "citigroup": "citibank n a",

    # Big auto
    "ford": "ford motor",
    "gm": "general motors",
    "general motors": "general motors",

    # Big consulting
    "deloitte": "deloitte consulting",
    "ey": "ernst & young u s",
    "ernst & young": "ernst & young u s",
    "pwc": "pricewaterhousecoopers advisory services",
    "accenture": "accenture",
    "capgemini": "capgemini america",

    # Lever-board brands that need explicit mapping
    "matchgroup": "match group americas",
    "match group": "match group americas",
    "tinder": "tinder",
    "discord": "discord",
    "anduril": "anduril",                        # may not be in LCA db; safe to alias

    # Big Indian outsourcing
    "cognizant": "cognizant technology solutions us",
    "infosys": "infosys",
    "tcs": "tata consultancy services",
    "tata consultancy services": "tata consultancy services",
    "wipro": "wipro",
    "hcl": "hcl america",
    "ltimindtree": "ltimindtree",
    "tech mahindra": "tech mahindra americas",
    "mphasis": "mphasis",
}


# Minimum query length BEFORE the prefix-LIKE layer fires. Below this,
# a short query like "a" would match thousands of rows. Exact + alias
# layers have no length floor (those use equality, not LIKE).
PREFIX_MIN_LEN = 3


async def lookup_employer(
    s: AsyncSession, raw_company_name: str
) -> tuple[H1BEmployer | None, str]:
    """Return (employer_or_None, match_layer).

    match_layer is one of: "alias" / "exact" / "prefix" / "miss".
    """
    norm = normalize_company_name(raw_company_name)
    if not norm:
        return None, "miss"

    # Layer 1: alias (run first so curated brand mappings beat any
    # accidental same-name small entity in the LCA data).
    aliased = EMPLOYER_ALIASES.get(norm)
    if aliased:
        row = (
            await s.execute(
                select(H1BEmployer).where(H1BEmployer.employer_name_normalized == aliased)
            )
        ).scalar_one_or_none()
        if row:
            return row, "alias"

    # Layer 2: exact normalized match
    row = (
        await s.execute(
            select(H1BEmployer).where(H1BEmployer.employer_name_normalized == norm)
        )
    ).scalar_one_or_none()
    if row:
        return row, "exact"

    # Layer 3: forward prefix-token LIKE — Adzuna name is a complete-word
    # prefix of the DB name. E.g. "amazon" matches "amazon com services".
    # Trailing space requires a token boundary so "data" can't match
    # "databricks". Length floor avoids over-broad matches.
    if len(norm) >= PREFIX_MIN_LEN:
        row = (
            await s.execute(
                select(H1BEmployer)
                .where(H1BEmployer.employer_name_normalized.like(f"{norm} %"))
                .order_by(H1BEmployer.lca_count_last_12mo.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row:
            return row, "prefix"

    # Layer 4: reverse prefix-token — DB name is a complete-word prefix of
    # the Adzuna name. E.g. Adzuna "Anduril Industries" should match a DB
    # row that's just "anduril". The leading-space-or-start guard prevents
    # matching unrelated short tokens lurking inside the Adzuna string.
    if len(norm) >= PREFIX_MIN_LEN:
        # Materialize the first 1-3 tokens of the Adzuna name as candidate
        # DB keys and look each up in priority order (shortest first wins
        # to handle the common "Brand + suffix words" pattern).
        tokens = norm.split()
        candidates = [" ".join(tokens[: i + 1]) for i in range(min(3, len(tokens)))]
        candidates = [c for c in candidates if len(c) >= PREFIX_MIN_LEN and c != norm]
        if candidates:
            row = (
                await s.execute(
                    select(H1BEmployer)
                    .where(H1BEmployer.employer_name_normalized.in_(candidates))
                    .order_by(H1BEmployer.lca_count_last_12mo.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row:
                return row, "reverse_prefix"

    return None, "miss"
