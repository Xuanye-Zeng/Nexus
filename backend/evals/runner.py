"""Apply invariants to cached (or live) LLM outputs.

Cache format on disk:
    evals/outputs/{module}/{case_id}.json
    {
      "case_id": "case_01_explicit_denial",
      "output": "raw LLM text",
      "model": "qwen2.5:14b",
      "prompt_version": 1,
      "input_metadata": {...}
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import CachedOutput, CaseResult, EvalReport
from .fixtures import (
    BulletRewriterFixture,
    SponsorshipFixture,
    load_bullet_rewriter_fixtures,
    load_sponsorship_fixtures,
)
from .invariants import bullet_rewriter as br_inv
from .invariants import sponsorship as sp_inv

_EVALS_ROOT = Path(__file__).resolve().parent
_OUTPUTS_ROOT = _EVALS_ROOT / "outputs"


def _cache_path(module: str, case_id: str) -> Path:
    return _OUTPUTS_ROOT / module / f"{case_id}.json"


def load_cached(module: str, case_id: str) -> CachedOutput | None:
    path = _cache_path(module, case_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return CachedOutput(
        case_id=data["case_id"],
        output=data["output"],
        model=data.get("model", "unknown"),
        prompt_version=data.get("prompt_version", "unknown"),
        input_metadata=data.get("input_metadata", {}),
    )


def save_cached(
    module: str,
    case_id: str,
    output: str,
    model: str,
    prompt_version: int | str,
    input_metadata: dict[str, Any] | None = None,
) -> Path:
    path = _cache_path(module, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "output": output,
                "model": model,
                "prompt_version": prompt_version,
                "input_metadata": input_metadata or {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return path


# ---- module-specific evaluators ----


def _eval_sponsorship_case(fx: SponsorshipFixture, output: str) -> CaseResult:
    results = [check(output, fx.jd_text) for check in sp_inv.ALL_INVARIANTS]
    return CaseResult(case_id=fx.case_id, results=results)


def _eval_bullet_rewriter_case(fx: BulletRewriterFixture, output: str) -> CaseResult:
    # bullet_rewriter invariants take only the output — the JD isn't needed
    # once we're validating structural properties of the rewrite itself.
    results = [check(output) for check in br_inv.ALL_INVARIANTS]
    return CaseResult(case_id=fx.case_id, results=results)


def evaluate_sponsorship_cached() -> EvalReport:
    report = EvalReport(module="sponsorship_classifier")
    for fx in load_sponsorship_fixtures():
        cached = load_cached("sponsorship", fx.case_id)
        if cached is None:
            report.cases.append(
                CaseResult(
                    case_id=fx.case_id,
                    results=[
                        _missing_cache_result(check.__name__)
                        for check in sp_inv.ALL_INVARIANTS
                    ],
                )
            )
            continue
        report.cases.append(_eval_sponsorship_case(fx, cached.output))
    return report


def evaluate_bullet_rewriter_cached() -> EvalReport:
    report = EvalReport(module="bullet_rewriter")
    for fx in load_bullet_rewriter_fixtures():
        cached = load_cached("bullet_rewriter", fx.case_id)
        if cached is None:
            report.cases.append(
                CaseResult(
                    case_id=fx.case_id,
                    results=[
                        _missing_cache_result(check.__name__)
                        for check in br_inv.ALL_INVARIANTS
                    ],
                )
            )
            continue
        report.cases.append(_eval_bullet_rewriter_case(fx, cached.output))
    return report


def _missing_cache_result(name: str):
    from .base import InvariantResult

    # Function names are `check_<invariant>`; strip prefix for cleaner report.
    short = name[len("check_") :] if name.startswith("check_") else name
    return InvariantResult(
        name=short,
        passed=False,
        detail="no cached output — run `python -m evals.run <module> --live`",
    )


def run_all_cached() -> dict[str, EvalReport]:
    return {
        "sponsorship_classifier": evaluate_sponsorship_cached(),
        "bullet_rewriter": evaluate_bullet_rewriter_cached(),
    }
