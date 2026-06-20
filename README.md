# Nexus

A personal job-search assistant built around a multi-agent core. Ingests jobs
from four sources, classifies visa sponsorship per posting, customizes my
resume against any JD, and surfaces it all behind a natural-language search
bar. Built as both a portfolio piece for AI Agent SDE roles and a tool I use
to find work.

> **Status:** v1.4 — M1 + M2 + M3 v1 + M5 v1.5 + M6 v1 shipped on `develop`. See
> [`NEXUS_TECHNICAL_PLAN.md`](./NEXUS_TECHNICAL_PLAN.md) for the canonical
> design + changelog (the document I write before every meaningful change).

---

## Why it exists

I'm an international student on F-1 OPT looking for SDE roles in the US.
Standard job boards waste my time — half the listings explicitly won't sponsor
H-1B, and there's no signal upfront about which employers actually file LCAs.
Nexus combines:

1. **Sponsorship verdict per JD** — JD-text classifier (LLM) + DOL OFLC LCA
   filing history (public CSV) + a 6-rule resolver (explicit JD denial
   overrides positive LCA history; strong LCA history overrides JD silence).
2. **Resume customization** — paste a JD, get bullets rewritten in the JD's
   language with every number preserved verbatim from my originals.
3. **Multi-agent natural-language interface** — one search bar that routes to
   the right capability (search jobs / customize resume / classify sponsorship
   / ingest more / triage emails) via a LangGraph state machine.

---

## Live numbers (as of v1.4)

| Metric | Value |
|---|---|
| Job sources (`@register_connector`) | **4** — Adzuna REST · Greenhouse JSON (24 boards) · Lever JSON (25 boards) · Workday CXS JSON (6 tenants) |
| Open jobs covered across registered sources | **~10K** |
| Agent tools (`@register_tool`) | **8** |
| DOL OFLC LCAs aggregated (3 fiscal years) | **404,756** certified H-1B-family rows |
| Unique H-1B employers indexed | **48,047** |
| Recent-12mo LCAs across all employers | **294,594** |
| Sponsorship classifier fixture pass | **5/5** |
| Master Agent intent classifier fixture pass | **11/11** |
| Email classifier fixture pass | **7/8** |
| `bullet_rewriter` prompt iterations | **9 versions** (v8 stable @ 1% bullet-level fail rate) |
| pgvector RAG (`top_k_sections_for_jd`) | median **2.34 ms** / p95 4.31 ms |

---

## Architecture

```
                       React (Vite + Tailwind v4)
                       Dashboard · /resume customize page
                        │
                        │ /api/* (axios + React Query)
                        ▼
                       FastAPI 1.4
              ┌─────────┴──────────┐
              │ POST /api/agent    │  ← natural-language entry
              │ POST /api/customize-resume
              │ GET  /api/overview · /jobs · /emails · /agent/runs · ...
              └──────────┬─────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Master Agent          │  LangGraph StateGraph
            │  classify_intent → router → 8 tool nodes → respond
            └─────┬──────────────┬───┘
                  │              │
                  ▼              ▼
         tools/* (registry)   services/* (business logic)
         search_jobs              ingest_pipeline  ← single source of truth
         customize_resume         employer_lookup  ← 4-layer brand→legal match
         classify_sponsorship     sponsorship      ← §6 6-rule resolver
         ingest_jobs              llm              ← per-purpose LLM_PROFILES
         rescore_listings         matching         ← top-K mean cosine
         triage_emails            retrieval        ← pgvector RAG
         delete_emails
         get_top_resume_sections_for_jd

                       │                                  │
                       ▼                                  ▼
              connectors/ (registry)             Postgres 16 + pgvector
              adzuna · greenhouse                Redis 7 (Celery broker)
              lever · workday                    Ollama (local LLM + embed)
                                                 Groq (cloud premium LLM)
```

**Hybrid LLM routing** via `services/llm.py`:

| Purpose | Provider | Model | Why |
|---|---|---|---|
| sponsorship_classifier | Ollama (local) | qwen2.5:14b | High-volume 4-class JSON, no rate limit |
| email_classifier | Ollama (local) | qwen2.5:14b | Same shape as sponsorship |
| master_intent_classifier | Ollama (local) | qwen2.5:14b | Routing per agent turn |
| master_responder | Ollama (local) | qwen2.5:14b @ T=0.3 | NL summary over structured tool output |
| bullet_rewriter | Groq (cloud) | llama-3.3-70b-versatile | Low volume, prompt-fidelity-sensitive |
| jd_keyword_extractor | Groq (cloud) | llama-3.3-70b-versatile | Same volume profile as rewriter |

Switching a task's backend is a one-line edit in `LLM_PROFILES`.

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19 · TypeScript · Tailwind CSS v4 (CSS-first `@theme`) · React Query · React Router · Recharts · Vite |
| Backend | FastAPI · SQLAlchemy 2.0 (async) · Alembic · pydantic-settings · httpx (async) |
| Data | Postgres 16 + **pgvector** · Redis 7 · Docker Compose |
| Agent | **LangGraph** StateGraph · **LangChain** core · Per-purpose `LLM_PROFILES` factory |
| LLMs | **Ollama** `qwen2.5:14b` + `nomic-embed-text` (local) · **Groq** `llama-3.3-70b-versatile` (cloud) |
| Background | **Celery** (4 staggered 6h beat tasks) |
| Observability | `agent_runs` table per invocation · `/api/agent/runs/stats` (avg + p95 via Postgres `percentile_cont`) · optional LangSmith via env vars |
| Job data | Adzuna REST · Greenhouse public JSON · Lever public JSON · Workday CXS JSON |
| Sponsorship | DOL OFLC LCA Disclosure Data (FY2024–FY2026 Q2) — pandas + openpyxl ingest |

---

## Key technical patterns

These each have a longer write-up in [`NEXUS_TECHNICAL_PLAN.md`](./NEXUS_TECHNICAL_PLAN.md).

### Pluggable connectors
`connectors/base.py` defines `JobConnector` (ABC) + `@register_connector`
decorator + a name→class registry. Adding a new job source is one file:
write a class, decorate it, import it. The orchestrator never learns about
specific sources.

### Pluggable agent tools
Same shape for agent capabilities. `tools/registry.py` + `@register_tool` —
each capability is a function that takes a dict and returns a dict.
`master_intent_classifier.v3` is the one place the LLM learns about new
tools.

### `LLM_PROFILES` factory
`services/llm.py` maps **purpose** → `(provider, model, temperature)`. Six
purposes registered. Switching a task's backend means editing one line; the
calling sites use `get_llm("purpose")` and don't care which provider runs.

### Brand-to-legal name matcher (4 layers)
Adzuna says "Amazon"; DOL LCA says "AMAZON.COM SERVICES LLC". The matcher
tries: **alias** (curated FAANG-tier brand→legal) → **exact** (normalized
equality) → **forward prefix** (Adzuna name is a complete-word prefix of
the DB name, e.g. "amazon" → "amazon com services") → **reverse prefix**
(DB name is a complete-word prefix of the Adzuna name, e.g. "anduril" → DB
"anduril"). 97% hit rate on FAANG-tier brands verified.

### Sponsorship §6 6-rule resolver
Combines JD-text signal with LCA filing history with a priority order that
favors the international student's interests: **explicit JD denial wins
over any positive LCA history** (an employer that says "no sponsorship" in
this posting won't sponsor for this role even if they file 100 LCAs/yr;
verified on a real Cyient listing where 35 LCAs/yr were overridden by JD
denial). Strong recent LCA history (≥5 in 12mo) wins when JD is silent.
Full table in plan §6.

### Hybrid local + cloud LLM
Detailed above. Decision driven by Groq's 100K-TPD free-tier ceiling
becoming a real blocker during batch ingest. Local `qwen2.5:14b` matches
Groq 70b accuracy on classification tasks (5/5 fixture pass) and removes
the daily cap; Groq stays for prompt-fidelity-sensitive rewriting where
the 70b is meaningfully better.

### Single ingest pipeline
`services/ingest_pipeline.py` is the only place the per-listing
classify + LCA lookup + embed + resolve + UPSERT chain lives. The CLI
script, the Master Agent `ingest_jobs` tool, and the Celery 6h task all
call `ingest_from_source()` — so a change to (say) the sponsorship prompt
lands once and propagates everywhere.

### Per-turn `agent_runs` observability
Every Master Agent invocation persists `{module, intent, status,
input_summary, response, tool_args (jsonb), tool_result_summary,
classifier_reasoning, error, latency_ms, langsmith_trace_id, created_at}`.
`GET /api/agent/runs/stats` returns avg + p95 latency via Postgres
`percentile_cont(0.95)`. When `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`
are set, the stored `langsmith_trace_id` matches LangChain's
`RunnableConfig.run_id` — click-through to LangSmith works.

---

## Quick start

### Prerequisites
- Docker Desktop (Postgres + Redis)
- Python 3.13
- Node 24+
- [Ollama](https://ollama.com) running locally with `qwen2.5:14b` + `nomic-embed-text` pulled
- Free [Groq API key](https://console.groq.com/) (free tier is fine)
- Free [Adzuna API credentials](https://developer.adzuna.com/admin/access_details)

### Run

```bash
# 1. Postgres + Redis
docker compose up -d

# 2. Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e . || pip install fastapi uvicorn sqlalchemy[asyncio] asyncpg alembic \
    pgvector langchain langchain-ollama langchain-groq langgraph httpx pandas openpyxl celery redis pydantic-settings
cp .env.example .env  # fill in GROQ_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY
venv/bin/alembic upgrade head
venv/bin/python -m scripts.seed_prompts
venv/bin/python -m scripts.seed_resume        # uses bundled fixture resume
venv/bin/python -m scripts.ingest_dol_lca     # ~3 fiscal years of LCA data, ~5 min
venv/bin/uvicorn main:app --reload

# 3. Celery (optional, for 6h auto-ingest)
venv/bin/celery -A celery_app worker --beat -l info

# 4. Frontend
cd ../frontend
npm install
npm run dev   # http://localhost:5173
```

### Try the agent (CLI)

```bash
cd backend
venv/bin/python -m scripts.run_master_agent "Show me sponsor-friendly ML jobs at Anthropic"
venv/bin/python -m scripts.run_master_agent "Pull more Greenhouse backend engineer jobs"
venv/bin/python -m scripts.run_master_agent --fixtures   # 6-case NL routing suite
```

### Try the agent (HTTP)

```bash
curl -X POST http://127.0.0.1:8000/api/agent \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me top sponsor-friendly Anthropic positions"}' | jq
```

### Health check (shows the full routing table)

```bash
curl http://127.0.0.1:8000/health | jq
```

---

## Roadmap

What's left from the milestones table in [`NEXUS_TECHNICAL_PLAN.md`](./NEXUS_TECHNICAL_PLAN.md):

- **M3 v1.5** — Microsoft Graph OAuth for real Outlook inbox sync (data model + classifier + tools all already work fixture-driven)
- **M4** — Microsoft Calendar OAuth + frontend month/week view (interview detection is already in the M3 email_classifier)
- **Frontend `/jobs` page** — full job feed with filter UI (dashboard's daily feed is the teaser)
- **Frontend `/agent` history viewer** — render `agent_runs` as a timeline with the p95 latency chart
- **Workday 422 tenants** — Amazon / JPMC / Capital One / others that reject the canonical CXS body shape; need tenant-specific facet payloads (≈3h reverse-engineering)
- **Match-score embedding upgrade** — swap nomic to `bge-m3` or `text-embedding-3-large` to widen the discrimination range (currently 0.45–0.60 cluster)
- **PDF export** from `/resume` page
- **Deployment** — Railway phase 1, then AWS ECS Fargate phase 2

---

## Documentation

- [`NEXUS_TECHNICAL_PLAN.md`](./NEXUS_TECHNICAL_PLAN.md) — the canonical design doc. Every meaningful change is preceded by a plan update + a changelog entry. The plan is the source of truth; the README is the welcome mat.

---

## License

MIT — but please don't redistribute the DOL LCA bulk-data CSVs through this
repo (they're a few hundred MB and the canonical source is
[dol.gov/agencies/eta/foreign-labor/performance](https://www.dol.gov/agencies/eta/foreign-labor/performance)).
The repository ignores `backend/data/dol_lca/` for this reason.
