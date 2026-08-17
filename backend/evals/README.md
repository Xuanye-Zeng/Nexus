# LLM invariant eval harness

Distinct from `backend/tests/` (deterministic unit pins). This module gates
**LLM output** against invariants — the things that MUST be true about a
rewrite / classification regardless of the specific input.

## Layout

```
evals/
├── base.py             InvariantResult / CaseResult / EvalReport / CachedOutput
├── fixtures.py         Loads JD text + expected labels for each module
├── invariants/
│   ├── sponsorship.py       5 invariants (json_parses / status_enum / …)
│   └── bullet_rewriter.py   5 invariants (structure / number_preservation / …)
├── outputs/            Committed cached LLM outputs (JSON files)
├── runner.py           Apply invariants to cached outputs
└── run.py              CLI entry point
```

## Modes

**Cached (default)** — fast, deterministic, no LLM required. Reads
`outputs/*.json`, applies invariants, prints report. This is what the pytest
gate in `backend/tests/test_evals.py` calls; CI blocks on regressions here.

**Live** — actually calls the LLM against every fixture, overwrites the cache,
then applies invariants. Run after a prompt edit.

```bash
# fast — cache mode
venv/bin/python -m evals.run sponsorship
venv/bin/python -m evals.run bullet_rewriter
venv/bin/python -m evals.run all

# regenerate cache from live LLM
venv/bin/python -m evals.run sponsorship --live      # needs Ollama running
venv/bin/python -m evals.run bullet_rewriter --live  # additionally needs Postgres (resume sections)
```

## Invariants

### `sponsorship_classifier`

| Name              | What it enforces |
|-------------------|------------------|
| `json_parses`      | Output parses via the same tolerance the production pipeline uses (raw / fenced / prose-wrapped JSON). |
| `status_enum`      | `status` ∈ {sponsors, no_sponsorship, us_citizen_only, unclear}. |
| `confidence_range` | `confidence` ∈ [0, 1]. |
| `cpt_opt_bool`     | `cpt_opt_signal` is `True` / `False` (not "yes", not 1). |
| `evidence_verbatim`| Either empty OR the exact substring appears in the JD (whitespace-normalized). Fabricated quotes would poison the "here's why we said sponsors" trust chain in the UI. |

### `bullet_rewriter`

| Name                    | What it enforces |
|-------------------------|------------------|
| `structure`             | `## PROJECTS`, `## EXPERIENCE`, `## SKILLS` all appear in order; at least one BEFORE/AFTER/REASON triple parseable. |
| `number_preservation`   | For every non-KEEP bullet, `number-set(AFTER) == number-set(BEFORE)`. Codifies prompt rule P4 — invented percentages ("15%" appearing in AFTER but not BEFORE) or dropped metrics both fail. |
| `no_forbidden_fillers`  | AFTER never contains `leverage`, `leveraging`, `utilize`, `utilizing`, `utilization`, `synergize`, `synergy`, or an em-dash. |
| `length_bounded`        | AFTER is not more than 2× BEFORE (or +60 chars for short bullets). Guards against dilution. |
| `skills_categories`     | `## SKILLS` section has exactly the 5 required categories in the fixed order: Programming Languages / Cloud & Infrastructure / Backend & Data / ML & AI / Core. |

## Adding a fixture

1. Drop a markdown JD file into `backend/fixtures/sponsorship_cases/case_NN_<label>.md`
   (label ∈ the 5 keys in `SPONSORSHIP_EXPECTED`) or `backend/fixtures/<name>.md`.
2. Register in `evals/fixtures.py` if it's a new module.
3. Run `--live` to populate the cache; commit the resulting `outputs/*.json`.

## Adding an invariant

1. Write a `check_<name>(output: str, ...) -> InvariantResult` in the module's
   invariant file.
2. Add it to `ALL_INVARIANTS`.
3. Add an adversarial pytest case in `backend/tests/test_evals.py` that proves
   the new invariant catches an obvious failure — a silently-vacuous invariant
   is worse than no invariant.

## Why this exists

`backend/tests/test_matching.py` pins `cosine_sim` — deterministic Python.
`backend/tests/test_sponsorship.py` pins the 6-rule resolver — deterministic
Python.

Neither of those knows anything about the LLM. This harness fills that gap:
it gates the fuzzy layer against structural properties that hold across all
inputs. When a prompt edit regresses (say, a v9 prompt starts hallucinating
percentages), pytest fails on `number_preservation` at the cached-mode gate.
