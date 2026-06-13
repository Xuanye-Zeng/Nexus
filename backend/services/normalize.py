"""Company name normalization for joining job listings against H-1B LCA data.

The same employer can appear with many surface forms across data sources:
  - "Amazon Web Services, Inc."
  - "Amazon Web Services Inc"
  - "AMAZON WEB SERVICES, INC"
  - "amazon web services"

normalize_company_name() collapses these to a single canonical key so
JobListing.company can JOIN H1BEmployer.employer_name_normalized.

Rules (in order):
  1. lowercase
  2. strip a single leading "the "
  3. strip trailing legal-form suffixes (inc/llc/corp/co/ltd/...)
     iteratively — a name may have "Inc., LLC" stacked
  4. remove all punctuation except inner & + spaces
  5. collapse internal whitespace
"""
from __future__ import annotations

import re

# Order matters — try longer / more specific suffixes first so e.g.
# "incorporated" is matched before "inc".
_LEGAL_SUFFIXES = (
    "incorporated",
    "corporation",
    "limited",
    "company",
    "holdings",
    "group",
    "llc",
    "l l c",
    "lp",
    "llp",
    "plc",
    "inc",
    "corp",
    "co",
    "ltd",
    "gmbh",
    "ag",
    "sa",
    "spa",
    "bv",
    "nv",
    "pty",
)

_LEGAL_SUFFIX_RE = re.compile(
    r"[\s,.]+(?:" + "|".join(_LEGAL_SUFFIXES) + r")\.?\s*$",
    re.IGNORECASE,
)

# Keep letters / digits / spaces / & / + (some company names have them legitimately,
# e.g. "AT&T", "C++ Foundation"). Strip everything else.
_PUNCT_RE = re.compile(r"[^a-z0-9 &+]+")

_WS_RE = re.compile(r"\s+")


def normalize_company_name(raw: str) -> str:
    """Return a stable lowercase key suitable for joining across data sources.

    Returns empty string for blank / null input.
    """
    if not raw:
        return ""

    name = raw.strip().lower()

    if name.startswith("the "):
        name = name[4:]

    # Iteratively strip trailing legal suffixes ("X, Inc., LLC" -> "X")
    while True:
        new = _LEGAL_SUFFIX_RE.sub("", name).strip()
        if new == name:
            break
        name = new

    name = _PUNCT_RE.sub(" ", name)
    name = _WS_RE.sub(" ", name).strip()
    return name
