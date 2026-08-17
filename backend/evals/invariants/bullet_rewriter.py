"""Invariants for `bullet_rewriter` LLM output.

The v8 prompt enforces strong preservation rules (P1-P4 in the prompt).
These invariants codify what a human reviewer would check on every rewrite:

  1. STRUCTURE — output has the three required section headers and every
     bullet has BEFORE / AFTER / REASON labels.
  2. NUMBER PRESERVATION — for every bullet, the set of numeric tokens in
     AFTER equals the set in BEFORE. Removing an existing metric or
     inventing a new one both fail this. This is the invariant users
     care about most: fabricating "15%" in AFTER is unrecoverable.
  3. NO FORBIDDEN FILLERS — AFTER lines must not contain the words the
     prompt bans (leverage, utilize, synergy, …). Includes em-dash check.
  4. KEEP SEMANTICS — when AFTER is literally "KEEP", the invariant passes
     trivially (KEEP is a legal signal, not a bullet to check).
  5. SKILLS CATEGORIES — the ## SKILLS section must have exactly the 5
     categories in the fixed order the prompt specifies.
  6. LENGTH BOUNDED — AFTER is not more than 2× the length of BEFORE
     (guards against runaway rewriting that dilutes the signal).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..base import InvariantResult

# ---- Regex + parsing helpers ----

# One number = digits, optional decimal, optional trailing % or 'x' multiplier,
# optional '+' suffix (e.g. "500+"). We intentionally ignore commas as thousands
# separators to keep the check simple — resume metrics rarely use them.
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?[+xX%]?")

# Forbidden filler words (case-insensitive whole-word match).
FORBIDDEN_WORDS = [
    "leverage",
    "leveraging",
    "utilize",
    "utilizing",
    "utilization",
    "synergize",
    "synergy",
]
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in FORBIDDEN_WORDS) + r")\b",
    re.IGNORECASE,
)
EM_DASH = "—"

# The prompt's 5 required Skills categories, in order.
REQUIRED_SKILL_CATEGORIES = [
    "Programming Languages",
    "Cloud & Infrastructure",
    "Backend & Data",
    "ML & AI",
    "Core",
]


@dataclass
class Bullet:
    """One (BEFORE, AFTER, REASON) triple extracted from the output."""

    before: str
    after: str
    reason: str


def extract_bullets(output: str) -> list[Bullet]:
    """Parse the bullet_rewriter output into (BEFORE, AFTER, REASON) triples.

    Mirrors the frontend's `parseRewrite.ts` logic. A bullet block looks like:
      - BEFORE: <text>
      AFTER: <text or KEEP>
      REASON: <text>

    Bullets separated by blank lines or by the next `- BEFORE:` marker.
    """
    bullets: list[Bullet] = []
    lines = output.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"-\s*BEFORE:\s*(.*)", line, re.IGNORECASE)
        if not m:
            i += 1
            continue
        before = m.group(1).strip()
        after = ""
        reason = ""
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if re.match(r"-\s*BEFORE:", nxt, re.IGNORECASE):
                break
            am = re.match(r"AFTER:\s*(.*)", nxt, re.IGNORECASE)
            rm = re.match(r"REASON:\s*(.*)", nxt, re.IGNORECASE)
            if am:
                after = am.group(1).strip()
            elif rm:
                reason = rm.group(1).strip()
            j += 1
        bullets.append(Bullet(before=before, after=after, reason=reason))
        i = j
    return bullets


def _numbers(s: str) -> set[str]:
    """Extract the set of numeric tokens (normalized) from a string."""
    return {m.group(0).lower() for m in _NUM_RE.finditer(s)}


# ---- Invariant checkers ----


def check_structure(output: str) -> InvariantResult:
    """The three required section headers appear in order."""
    required = ["## PROJECTS", "## EXPERIENCE", "## SKILLS"]
    positions = [output.find(h) for h in required]
    missing = [h for h, p in zip(required, positions) if p == -1]
    if missing:
        return InvariantResult(
            name="structure",
            passed=False,
            detail=f"missing headers: {missing}",
        )
    if not (positions[0] < positions[1] < positions[2]):
        return InvariantResult(
            name="structure",
            passed=False,
            detail=f"headers out of order: {list(zip(required, positions))}",
        )
    # Also require at least one BEFORE/AFTER/REASON triple parseable.
    if not extract_bullets(output):
        return InvariantResult(
            name="structure",
            passed=False,
            detail="no BEFORE/AFTER/REASON triples parseable",
        )
    return InvariantResult(name="structure", passed=True)


def check_number_preservation(output: str) -> InvariantResult:
    """For every non-KEEP bullet: number-set(AFTER) == number-set(BEFORE)."""
    bullets = extract_bullets(output)
    if not bullets:
        return InvariantResult(
            name="number_preservation",
            passed=False,
            detail="no bullets to check",
        )
    problems: list[str] = []
    for b in bullets:
        if b.after.upper().strip() == "KEEP":
            continue
        before_nums = _numbers(b.before)
        after_nums = _numbers(b.after)
        if before_nums != after_nums:
            added = after_nums - before_nums
            dropped = before_nums - after_nums
            problems.append(
                f"{b.before[:40]!r}: added={sorted(added)} dropped={sorted(dropped)}"
            )
    if problems:
        return InvariantResult(
            name="number_preservation",
            passed=False,
            detail="; ".join(problems[:5]),
        )
    return InvariantResult(name="number_preservation", passed=True)


def check_no_forbidden_fillers(output: str) -> InvariantResult:
    """AFTER lines must not contain leverage / utilize / synergy / em-dash."""
    bullets = extract_bullets(output)
    if not bullets:
        return InvariantResult(
            name="no_forbidden_fillers",
            passed=False,
            detail="no bullets to check",
        )
    problems: list[str] = []
    for b in bullets:
        if b.after.upper().strip() == "KEEP":
            continue
        hits = _FORBIDDEN_RE.findall(b.after)
        if hits:
            problems.append(f"{b.after[:40]!r}: {sorted(set(h.lower() for h in hits))}")
        if EM_DASH in b.after:
            problems.append(f"{b.after[:40]!r}: em-dash")
    if problems:
        return InvariantResult(
            name="no_forbidden_fillers",
            passed=False,
            detail="; ".join(problems[:5]),
        )
    return InvariantResult(name="no_forbidden_fillers", passed=True)


def check_length_bounded(output: str) -> InvariantResult:
    """AFTER length <= 2 × BEFORE length (chars). Guards against dilution."""
    bullets = extract_bullets(output)
    if not bullets:
        return InvariantResult(
            name="length_bounded",
            passed=False,
            detail="no bullets to check",
        )
    problems: list[str] = []
    for b in bullets:
        if b.after.upper().strip() == "KEEP":
            continue
        if not b.before:
            continue
        # Small bullets get a floor so we don't flag +50 chars on a 20-char BEFORE.
        limit = max(2 * len(b.before), len(b.before) + 60)
        if len(b.after) > limit:
            problems.append(
                f"{b.before[:30]!r}: after={len(b.after)} > limit={limit}"
            )
    if problems:
        return InvariantResult(
            name="length_bounded",
            passed=False,
            detail="; ".join(problems[:5]),
        )
    return InvariantResult(name="length_bounded", passed=True)


def check_skills_categories(output: str) -> InvariantResult:
    """## SKILLS section has exactly the 5 required categories in order."""
    m = re.search(r"##\s*SKILLS\s*\n(.*)", output, re.IGNORECASE | re.DOTALL)
    if not m:
        return InvariantResult(
            name="skills_categories",
            passed=False,
            detail="no ## SKILLS section",
        )
    skills_block = m.group(1)
    # Categories are the leading word(s) before the first colon on each line.
    found: list[str] = []
    for line in skills_block.splitlines():
        stripped = line.strip().lstrip("-").strip()
        cm = re.match(r"([A-Za-z][A-Za-z0-9 &+/-]*?):", stripped)
        if cm:
            found.append(cm.group(1).strip())
    if found != REQUIRED_SKILL_CATEGORIES:
        return InvariantResult(
            name="skills_categories",
            passed=False,
            detail=f"got {found}, expected {REQUIRED_SKILL_CATEGORIES}",
        )
    return InvariantResult(name="skills_categories", passed=True)


ALL_INVARIANTS = [
    check_structure,
    check_number_preservation,
    check_no_forbidden_fillers,
    check_length_bounded,
    check_skills_categories,
]

# HARD invariants are correctness/safety — a failure means the pipeline
# produced output that's wrong or unsafe to ship. CI must block on these.
# SOFT invariants are style — filler words or dilution. LLM occasionally
# slips despite the prompt ban; we track the failure rate over time
# instead of blocking every commit on a stochastic style regression.
HARD_INVARIANTS = [
    check_structure,
    check_number_preservation,
    check_skills_categories,
]

SOFT_INVARIANTS = [
    check_no_forbidden_fillers,
    check_length_bounded,
]
