"""Fixture loaders + expected metadata for the eval harness."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

SPONSORSHIP_DIR = _BACKEND_ROOT / "fixtures" / "sponsorship_cases"

# Filename token → (expected_status, expected_cpt_opt) for sponsorship fixtures.
# Kept in lockstep with scripts/run_sponsorship_classifier.py.
SPONSORSHIP_EXPECTED: dict[str, tuple[str, bool]] = {
    "explicit_denial": ("no_sponsorship", False),
    "explicit_sponsors": ("sponsors", True),
    "clearance_required": ("us_citizen_only", False),
    "silent": ("unclear", False),
    "intern_cpt": ("sponsors", True),
}


@dataclass
class SponsorshipFixture:
    case_id: str
    jd_text: str
    expected_status: str
    expected_cpt_opt: bool


def load_sponsorship_fixtures() -> list[SponsorshipFixture]:
    out: list[SponsorshipFixture] = []
    for path in sorted(SPONSORSHIP_DIR.glob("case_*.md")):
        m = re.match(r"case_\d+_(.+)\.md", path.name)
        if not m:
            continue
        key = m.group(1)
        if key not in SPONSORSHIP_EXPECTED:
            continue
        expected_status, expected_cpt = SPONSORSHIP_EXPECTED[key]
        out.append(
            SponsorshipFixture(
                case_id=path.stem,
                jd_text=path.read_text(),
                expected_status=expected_status,
                expected_cpt_opt=expected_cpt,
            )
        )
    return out


# ---- bullet_rewriter ----

BULLET_REWRITER_JD_DIR = _BACKEND_ROOT / "fixtures"


@dataclass
class BulletRewriterFixture:
    case_id: str
    jd_text: str
    # The rewriter reads resume sections from the DB — for cached-mode we only
    # need the JD (input) and can trust the cached output was produced by the
    # real pipeline.


def load_bullet_rewriter_fixtures() -> list[BulletRewriterFixture]:
    """Currently one fixture: the Amazon SDE JD used throughout M1 iteration."""
    jd_path = BULLET_REWRITER_JD_DIR / "jd_amazon_sde.md"
    if not jd_path.exists():
        return []
    return [
        BulletRewriterFixture(
            case_id="amazon_sde",
            jd_text=jd_path.read_text(),
        )
    ]
