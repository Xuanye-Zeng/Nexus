"""LLM output invariant eval harness.

Two-mode design:
  - `cached` (default): read committed LLM outputs from `evals/outputs/` and run
    invariants against them. Fast, deterministic, no LLM required — this is
    what pytest + CI use to gate prompt/pipeline changes.
  - `live`: actually call the LLM against every fixture, regenerate the cache,
    then apply the same invariants. Slower (~30s for sponsorship, ~30s per
    bullet_rewriter fixture) — run manually after prompt edits.

Distinct from `backend/tests/`:
  - `tests/` pins pure Python functions (deterministic, unit-scale).
  - `evals/` gates LLM outputs against invariants (non-deterministic surface,
    behavior-scale). One-shot in CI via `tests/test_evals.py` which just
    calls `runner.run(cached=True)` and asserts pass_rate >= threshold.
"""
