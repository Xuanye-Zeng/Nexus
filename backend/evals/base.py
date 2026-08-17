"""Base types for the invariant eval harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InvariantResult:
    """One invariant × one case = one result."""

    name: str
    passed: bool
    detail: str = ""  # human-readable reason on failure (or "" on pass)


@dataclass
class CaseResult:
    """All invariants applied to one (fixture, cached_output) pair."""

    case_id: str
    results: list[InvariantResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def n_pass(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def n_total(self) -> int:
        return len(self.results)


@dataclass
class EvalReport:
    """Aggregate report across all cases for one module (e.g. sponsorship)."""

    module: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def n_checks(self) -> int:
        return sum(c.n_total for c in self.cases)

    @property
    def n_pass(self) -> int:
        return sum(c.n_pass for c in self.cases)

    @property
    def pass_rate(self) -> float:
        return self.n_pass / self.n_checks if self.n_checks else 1.0

    @property
    def failed_cases(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.passed]

    def render(self) -> str:
        """Pretty table for CLI + pytest failure messages."""
        if not self.cases:
            return f"{self.module}: no cases\n"

        invariant_names = [r.name for r in self.cases[0].results]
        col_case = max(len("case"), max(len(c.case_id) for c in self.cases))
        col_inv = max(6, max(len(n) for n in invariant_names))

        lines = [
            f"{self.module} · {len(self.cases)} cases × {len(invariant_names)} invariants",
            "",
            f"{'case':<{col_case}}  " + "  ".join(n.ljust(col_inv) for n in invariant_names),
            "-" * (col_case + 2 + (col_inv + 2) * len(invariant_names)),
        ]
        for c in self.cases:
            row = f"{c.case_id:<{col_case}}  "
            row += "  ".join(
                ("PASS" if r.passed else "FAIL").ljust(col_inv) for r in c.results
            )
            lines.append(row)

        lines.append("")
        lines.append(
            f"Overall: {self.n_pass}/{self.n_checks} pass ({self.pass_rate * 100:.1f}%)"
        )

        # Failure detail block
        if self.failed_cases:
            lines.append("")
            lines.append("FAILURES:")
            for c in self.failed_cases:
                for r in c.results:
                    if not r.passed:
                        lines.append(f"  {c.case_id} :: {r.name} — {r.detail}")

        return "\n".join(lines) + "\n"


# ---------- Cache format ----------


@dataclass
class CachedOutput:
    """One (fixture_id, LLM output) row stored on disk."""

    case_id: str
    output: str
    model: str
    prompt_version: int | str
    input_metadata: dict[str, Any] = field(default_factory=dict)
