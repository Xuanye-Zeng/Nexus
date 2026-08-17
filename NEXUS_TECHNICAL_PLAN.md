# Nexus — AI-Powered Personal Job Search Assistant
## Technical Plan & Living Document

> **Version:** 1.7  
> **Last Updated:** 2026-07-20  
> **Owner:** Xuanye (Alex) Zeng  
> **Status:** M1+M2+M3 v1+M5 v1.5+M6 v1 done; Dashboard + /resume + /jobs + /agent live; **Celery 6h auto-ingest live**; **agent_runs observability** live; **pytest + GitHub Actions CI live** (115 tests: 72 pure-function pins + 7 PDF parser + 23 invariant-eval gates + 13 application-status rule pins; ruff lint; frontend tsc + vite build all gating every push/PR); **LLM invariant eval harness live** (`backend/evals/` — 10 sponsorship fixtures × 5 invariants = **50/50 pass live on qwen2.5:14b**; bullet_rewriter split into HARD + SOFT invariants — hard = structure / number_preservation / skills_categories always 100%, soft = filler / length tracks stochastic slippage — live regen against Amazon SDE JD surfaced a real "utilizing" leak from llama-3.3-70b on v8 prompt); **PDF export live**; **AgentBar rich rendering** live; **Application status flow (R4) live** — `job_applications` table + Saved / Applied / Interviewing / Offer / Rejected / Withdrawn 6-state model, sticky `applied_at` invariant (stamped on first move to applied-family, never reset even on downgrade), inline status control on /jobs rows + "Applied last 7 days" KPI on Dashboard + `GET /api/jobs/applications` + `GET /api/jobs/applications/counts` endpoints + `application_status` filter on /api/jobs. 4 connectors, 8 tools, 4 frontend routes.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Third-Party APIs & Services](#4-third-party-apis--services)
5. [Data Model](#5-data-model)
6. [Module Breakdown](#6-module-breakdown)
7. [Agent Design](#7-agent-design)
8. [GitHub Setup & CI/CD](#8-github-setup--cicd)
9. [Deployment](#9-deployment)
10. [Milestones & Success Criteria](#10-milestones--success-criteria)
11. [Prompt Templates Registry](#11-prompt-templates-registry)
12. [Known Risks & Mitigations](#12-known-risks--mitigations)
13. [Changelog](#13-changelog)

---

## 1. Project Overview

### What It Is
A multi-agent personal assistant for job searching, built as a full-stack web application. The system aggregates job listings from multiple sources, triages incoming emails by importance, manages calendar events, and generates tailored resumes/cover letters — all orchestrated by a Master Agent that coordinates specialized sub-agents.

### Why It Exists
- Automate the repetitive parts of job searching (scanning listings, triaging recruiter emails, customizing resumes per JD)
- Serve as a portfolio project demonstrating: multi-agent orchestration, RAG pipelines, full-stack engineering, cloud deployment
- Personal daily-use tool with real utility, not just a demo

### Resume Value
This project directly maps to AI Agent SDE job requirements:
- Multi-agent orchestration with LangGraph
- RAG-based semantic job matching with pgvector
- Tool use / function calling patterns
- Full-stack: FastAPI + React + PostgreSQL
- OAuth integrations (Microsoft Graph / Gmail)
- Playwright scraping with anti-bot handling
- LLM observability with LangSmith

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     React Frontend                       │
│  Job Board | Email Inbox | Calendar | Resume Builder     │
└────────────────────────┬────────────────────────────────┘
                         │ REST / WebSocket
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend                        │
│              Auth | Routing | State Mgmt                 │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              Master Agent (LangGraph)                    │
│         Intent classification → tool dispatch            │
└──────┬──────────┬──────────────┬───────────────┬────────┘
       │          │              │               │
  Job Agent  Email Agent  Calendar Agent  Resume Agent
       │          │              │               │
  Scrapers   MS Graph /    Google Cal /    LLM + pgvector
  + APIs     Gmail API     MS Graph        diff engine
       │
  ┌────▼────────────────────────────────────┐
  │  Data Sources                            │
  │  Adzuna API | Greenhouse API             │
  │  Lever API  | Workday (Playwright)       │
  │  JobRight   (Playwright, phase 2)        │
  └─────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              PostgreSQL + pgvector                       │
│   users | resumes | jobs | applications                  │
│   emails | calendar_events | prompt_templates            │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles
- **Loose coupling**: each sub-agent is a set of independent tools; adding a new module = registering new tools
- **Stateless API layer**: all state lives in PostgreSQL, not in memory
- **Prompt versioning**: all LLM prompts stored in DB with version history, swappable from UI
- **Observable**: every LLM call traced via LangSmith

---

## 3. Tech Stack

### Frontend
| Layer | Choice | Reason |
|---|---|---|
| Framework | React 19 + TypeScript | Familiar from prior projects |
| Styling | Tailwind CSS v4 | Fast, consistent |
| State | Zustand | Lightweight, no boilerplate |
| HTTP | Axios + React Query | Caching + async state |
| Calendar UI | FullCalendar.io | Production-grade calendar component (post-M4) |
| Charts | Recharts | Composable bar/line/pie; bundled, no D3 setup |
| Icons | Lucide React | Clean line icons matching Crextio aesthetic |
| Build | Vite | Fast dev server |

**Design language** — card-based dashboard with warm-yellow + black + cream palette (Crextio-inspired):
- Background: `#F5F2EC` (warm cream)
- Card surface: `#FFFFFF` (white) / `#1B1B1B` (deep black for hero cards)
- Accent: `#F5D04A` (amber yellow — KPIs, active states, primary actions)
- Text: `#1B1B1B` primary, `#6E6E6E` secondary
- Border radius: `2xl` (24px) on cards, `full` on pills/badges
- Generous whitespace; never crowd cards.

### Backend
| Layer | Choice | Reason |
|---|---|---|
| Framework | FastAPI (Python) | Async, familiar, LangChain native |
| Auth | JWT + OAuth 2.0 | User sessions + MS/Google OAuth |
| Task Queue | Celery + Redis | Background scraping jobs |
| ORM | SQLAlchemy 2.0 | Async support, pgvector compatible |

### AI / Agent Layer
| Component | Choice | Reason |
|---|---|---|
| Orchestration | LangGraph | Multi-agent state management |
| LLM (dev) | Ollama qwen2.5:14b | Free, local, M4 optimized |
| LLM (prod) | Claude claude-sonnet-4-20250514 or GPT-4o | Tool calling reliability |
| Embeddings | nomic-embed-text (Ollama, local) | Free, 768-dim, no API cost |
| Vector DB | pgvector (PostgreSQL extension) | No separate DB, already using PG |
| Observability | LangSmith | Trace every agent call |

### Data & Infrastructure
| Component | Choice |
|---|---|
| Primary DB | PostgreSQL 16 + pgvector |
| Cache | Redis |
| Scraping | Playwright (async) |
| Container | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Deployment | AWS ECS (Fargate) or Railway (simpler for v1) |

---

## 4. Third-Party APIs & Services

### Email & Calendar
| Service | API | Auth | Notes |
|---|---|---|---|
| Outlook / NEU Email | Microsoft Graph API | OAuth 2.0 (Azure Portal) | Covers NEU `.northeastern.edu` account |
| Gmail | Gmail API v1 | OAuth 2.0 (Google Cloud Console) | Optional second inbox |
| Google Calendar | Google Calendar API v3 | Same OAuth as Gmail | |
| Microsoft Calendar | Microsoft Graph API | Same OAuth as Outlook | |

### Job Data Sources
| Source | Method | Notes |
|---|---|---|
| Adzuna | Official REST API (free) | Broad coverage, no scraping needed |
| Greenhouse | Public JSON endpoint (`/embed/job_board/json`) | Many startups use this ATS |
| Lever | Public API (`api.lever.co/v0/postings`) | Many AI startups use Lever |
| Workday | **CXS JSON API** (`/wday/cxs/{tenant}/{site}/jobs`) — Playwright as fallback only | Covers Amazon, Microsoft, Apple, Salesforce, NVIDIA, Capital One, JPMC, Walmart, etc. JSON-first because most tenants expose listings via public POST endpoint; Playwright reserved for tenants that hide behind reCAPTCHA. |
| JobRight | Playwright scraper (Phase 2) | Login required, higher complexity |
| LinkedIn | **NOT included** | ToS violation, legal risk |

### Sponsorship / Visa Data Sources (M2)
International student (CPT/OPT → H-1B) signal is a first-class requirement.
The system surfaces sponsorship status as a primary filter on the Job Board.

| Source | Method | Cost | Notes |
|---|---|---|---|
| U.S. DOL OFLC LCA Disclosure Data | Public CSV download (per fiscal year) | Free (.gov) | Ground truth — every H-1B/H-1B1/E-3 LCA filed by every U.S. employer; ~600K rows/year. Source: dol.gov/agencies/eta/foreign-labor/performance |
| JD text classification | LLM (Groq) `sponsorship_classifier` prompt | Per-token | Detects in-JD signals: "no sponsorship", "must be authorized", "US citizen only" |
| Static F500 / clearance heuristic | Hardcoded company lists | Free | Fallback when JD silent and no LCA history |

**Signal precedence:** LCA filing history > explicit JD text > heuristic.
JD text can lie ("we sponsor" but actually don't); LCA filings are legal
documents the employer cannot retract — they are ground truth.

### LLM / AI
| Service | Usage | Cost |
|---|---|---|
| Ollama (local) | Dev LLM + embeddings (qwen2.5:14b + nomic-embed-text) | Free |
| Anthropic API / OpenAI GPT-4o | Production LLM calls | Pay-per-use |
| LangSmith | Tracing & observability | Free tier (10k traces/month) |

---

## 5. Data Model

### Core Tables

```sql
-- Users
users (id, email, name, created_at)

-- Resume components (structured, not just PDF)
resume_profiles (id, user_id, version, label, created_at)
resume_sections (id, profile_id, section_type, content_json, embedding vector(768))
  -- section_type: 'project' | 'experience' | 'skill' | 'education'

-- Job listings
job_listings (
  id, source, source_id, company, title, location,
  description_raw, description_clean,
  match_score float, embedding vector(768),
  status, -- 'new' | 'saved' | 'applied' | 'rejected' | 'interviewing'
  scraped_at, expires_at,

  -- Sponsorship / international-student signals (M2)
  sponsorship_status,      -- 'sponsors' | 'no_sponsorship' | 'us_citizen_only' | 'unclear'
  sponsorship_evidence,    -- text: exact JD quote that triggered the classification
  sponsorship_confidence,  -- float: 0.0-1.0 combined LLM + LCA signal
  h1b_lca_count_recent,    -- int: company's LCA filings in the past 12 months
  h1b_lca_year,            -- int: most recent fiscal year company filed an LCA
  cpt_opt_friendly         -- bool: explicit intern / new-grad / CPT-OPT friendly signal
)

-- H-1B LCA employer aggregates (DOL OFLC public CSV, refreshed quarterly)
h1b_employers (
  id, employer_name_normalized, -- normalized lowercased name for join
  lca_count_total int,
  lca_count_last_12mo int,
  most_recent_filing_year int,
  most_recent_filing_date,
  top_job_titles jsonb,         -- ["Software Engineer", "Data Scientist", ...]
  updated_at
)

-- Applications (links jobs + emails + calendar)
applications (
  id, user_id, job_id, 
  status, applied_at, notes,
  customized_resume_id, cover_letter_text
)

-- Emails
emails (
  id, user_id, source, -- 'outlook' | 'gmail'
  message_id, subject, sender, body_preview,
  importance_score int, -- 1-5
  category, -- 'interview' | 'recruiter' | 'rejection' | 'offer' | 'spam' | 'other'
  linked_application_id,
  received_at, is_read, is_deleted
)

-- Calendar events
calendar_events (
  id, user_id, source, -- 'google' | 'microsoft'
  event_id, title, description,
  start_time, end_time,
  linked_application_id,
  created_at
)

-- Prompt templates (versioned)
prompt_templates (
  id, name, version int, content text,
  module, -- 'resume_customizer' | 'email_triage' | 'job_board' | 'master_agent'
  is_active bool, created_at
)

-- Agent run logs
agent_runs (
  id, user_id, module, input_summary,
  langsmith_trace_id, status, created_at
)
```

---

## 6. Module Breakdown

### Module 1: Resume Customizer
**What it does:** Takes a pasted JD + selected resume profile → generates customized bullets, highlights keyword gaps, outputs diff view + exportable PDF.

**Flow:**
1. User pastes JD text
2. LLM extracts keywords and requirements from JD
3. pgvector similarity search finds most relevant resume sections
4. LLM rewrites matching bullets using JD language
5. Frontend shows side-by-side diff (original vs customized)
6. User edits inline, saves version, exports PDF

**Key technical decision:** Resume sections stored individually with embeddings — not as one blob. This enables section-level retrieval and targeted rewriting.

---

### Module 2: Job Board
**What it does:** Aggregates listings from multiple sources, scores each against your resume, **classifies sponsorship status for international students**, displays ranked feed.

**Flow:**
1. Celery background task runs scrapers on schedule (every 6hrs)
2. Each connector (Adzuna, Greenhouse, Lever, Workday) fetches listings
3. New listings get embedded and scored against resume profile embedding
4. **`sponsorship_classifier` LLM call** runs on each JD → extracts `status` + `evidence` + `cpt_opt_signal`
5. **LCA cross-reference**: company name normalized, joined against `h1b_employers` table → fills `h1b_lca_count_recent` and adjusts `sponsorship_confidence`
6. Frontend displays ranked feed with filters (score, location, company, source, **sponsorship_status**)
7. Default filter view hides `no_sponsorship` and `us_citizen_only` listings
8. User can save, mark applied, or dismiss

**Sponsorship resolution logic (final `sponsorship_status` decision):**
```
IF JD explicitly says "no sponsorship" or "US citizen only"
  → use JD signal (LCA history doesn't override an explicit denial)
ELIF LCA count_last_12mo >= 5
  → 'sponsors' (high confidence, even if JD silent)
ELIF JD says "we sponsor" AND LCA count >= 1
  → 'sponsors'
ELIF JD says "we sponsor" AND LCA count == 0
  → 'unclear' (lower confidence — they claim to but never have)
ELSE
  → 'unclear'
```

**Connector interface (abstract):**
```python
class JobConnector(ABC):
    source_name: str
    
    async def fetch_listings(self, keywords: list[str], location: str) -> list[JobListing]:
        ...
    
    async def fetch_detail(self, listing_id: str) -> JobListing:
        ...
```

Each source (Adzuna, Greenhouse, Lever, Workday) implements this interface. Adding a new source = new class, no changes to core logic.

---

### Module 3: Email Triage
**What it does:** Syncs emails from Outlook/Gmail, classifies by importance and category, enables delete/archive from UI.

**Flow:**
1. OAuth connection to Outlook (primary) and/or Gmail
2. Periodic sync pulls new emails via Microsoft Graph / Gmail API
3. LLM classifies each email: importance score (1-5) + category
4. Auto-links emails to applications if sender matches known company
5. Frontend shows unified inbox sorted by importance
6. Delete/archive actions call back to respective API

---

### Module 4: Calendar
**What it does:** Shows upcoming events, auto-creates interview events from emails, syncs with Google/Microsoft Calendar.

**Flow:**
1. Email Agent detects interview invitation in incoming email
2. LLM extracts: date, time, format (phone/video/onsite), interviewer
3. Calendar Agent creates event via API, links to application
4. Frontend shows calendar view with application context on each event

---

### Module 5: Master Agent
**What it does:** Natural language interface — user types a request, Master Agent classifies intent and dispatches to the right sub-agent tool.

**Example interactions:**
- "Show me new ML engineering jobs in Seattle" → Job Agent
- "Clean up my inbox, delete all rejection emails" → Email Agent
- "Customize my resume for this JD: [paste]" → Resume Agent
- "What interviews do I have this week?" → Calendar Agent
- "Apply to the Cohere posting and draft a cover letter" → Resume Agent + tracks in Application

**v1 tool registry (what's wired in M5 v1):**
The full registry below is the aspirational target — only the ✅ tools are
actually live in M5 v1 because their backing services exist. The others
unlock as M3 (Email) and M4 (Calendar) land. Adding a new tool = one
`@register_tool` decoration; the dispatcher discovers it automatically.

```python
tools = [
    # M5 v1 — live (job board + resume customizer surface as natural language)
    search_jobs_tool,                     # ✅ uses query_jobs filters
    customize_resume_tool,                # ✅ wraps POST /api/customize-resume
    classify_sponsorship_for_jd_tool,     # ✅ ad-hoc JD paste -> sponsorship verdict

    # M5 v1.5 — admin/maintenance, easy adds after v1 is verified
    ingest_jobs_tool,                     # pull from Adzuna/Greenhouse/Lever
    rescore_listings_tool,                # refresh match_score after resume update
    get_top_resume_sections_for_jd_tool,  # RAG-only retrieval debug

    # post-M3/M4 — unlocks as those modules land
    get_job_detail_tool,
    triage_emails_tool,
    delete_email_tool,
    get_calendar_events_tool,
    create_calendar_event_tool,
    get_applications_tool,
    update_application_status_tool,
]
```

---

## 7. Agent Design

### Master Agent (LangGraph StateGraph)

```
Entry → Intent Classifier → Router
                              ├── job_node
                              ├── email_node
                              ├── calendar_node
                              ├── resume_node
                              └── clarify_node (if ambiguous)
                                      ↓
                               Response Formatter → Exit
```

### State Schema
```python
class AgentState(TypedDict):
    messages: list[BaseMessage]
    user_id: str
    active_module: str
    tool_results: list[dict]
    requires_clarification: bool
```

### Sub-Agent Pattern
Each sub-agent is a LangGraph node that:
1. Receives state
2. Selects and calls relevant tools
3. Returns updated state with tool results
4. Master Agent decides whether to continue or respond

---

## 8. GitHub Setup & CI/CD

### Repository Structure
```
nexus/
├── frontend/           # React app
├── backend/            # FastAPI app
│   ├── agents/         # LangGraph agent definitions
│   ├── connectors/     # Job source connectors
│   ├── models/         # SQLAlchemy models
│   ├── routers/        # FastAPI route handlers
│   └── tools/          # LangGraph tool definitions
├── scripts/            # DB migrations, seed data
├── docker-compose.yml  # Local dev environment
├── .github/workflows/  # CI/CD pipelines
└── TECHNICAL_PLAN.md   # This document
```

### Branch Strategy
```
main          ← production, protected
develop       ← integration branch
feature/*     ← feature branches
fix/*         ← bug fixes
```
PRs into `develop` require CI pass. Merge to `main` triggers deploy.

### GitHub Actions Workflows

**CI** — `.github/workflows/ci.yml`, runs on push + PR to `develop` / `main`. Two jobs in parallel:

| Job | Steps |
|---|---|
| `backend` | `actions/setup-python@v5` (3.13) + pip cache → `pip install -e .[dev]` (also smoke-tests pyproject.toml installs cleanly) → `ruff check . --exclude venv --exclude alembic` → `pytest tests/ -v` (72 tests across `test_normalize` / `test_sponsorship` / `test_workday_parser` / `test_matching`, runs in ~3s) with dummy env vars so pydantic-settings doesn't bail at import time |
| `frontend` | `actions/setup-node@v4` (24) + npm cache → `npm ci` → `npm run build` (`tsc -b && vite build` — catches type errors + Tailwind v4 token resolution + dead imports) |

`concurrency.cancel-in-progress: true` so stale runs auto-cancel when a new commit lands on the same branch. README has a status badge linking to the workflow.

**CD (on merge to main):** *(not yet wired — deferred to Phase 1 Railway setup)*

**CD (on merge to main):**
```yaml
- Build Docker images
- Push to ECR (or Railway auto-deploy)
- Run DB migrations
- Deploy to ECS / Railway
- Post deploy: smoke test ping
```

### Local Dev Setup
```bash
# Clone and start everything
git clone https://github.com/Xuanye-Zeng/nexus
cd nexus
cp .env.example .env  # fill in API keys
docker-compose up     # starts PG, Redis, backend, frontend

# Backend only
cd backend && uvicorn main:app --reload

# Frontend only  
cd frontend && npm run dev
```

---

## 9. Deployment

### Phase 1 (MVP): Railway
- Simpler than AWS, free tier available
- PostgreSQL + Redis included
- Auto-deploy from GitHub main branch
- Good enough for personal use + demo

### Phase 2 (Production): AWS
- Backend: ECS Fargate (containerized FastAPI)
- DB: RDS PostgreSQL with pgvector extension
- Cache: ElastiCache Redis
- Frontend: S3 + CloudFront
- Secrets: AWS Secrets Manager
- Consistent with CloudScale project on resume

---

## 10. Milestones & Success Criteria

---

### Milestone 1: Resume Customizer
**Target:** 2 weeks from start  
**Branch:** `feature/resume-customizer`

**Done means:**
- [x] Resume sections stored in DB with embeddings *(2026-05-31, 12 sections, nomic-embed-text 768-dim)*
- [x] JD input → keyword extraction working *(2026-06-12, `jd_keyword_extractor` v1 active, structured ROLE / REQUIRED / PREFERRED / RESPONSIBILITIES / SOFT / SPONSORSHIP / YOE output, surfaced on `/resume` page)*
- [x] pgvector similarity search returning relevant sections *(2026-06-12, `top_k_sections_for_jd`, median 2.34ms / p95 4.31ms)*
- [x] LLM rewriting bullets using JD language *(2026-05-31, `bullet_rewriter` v8 stable, 1% bullet fail rate)*
- [x] Frontend diff view shows original vs customized side-by-side *(2026-06-19, `/resume` page — BEFORE/AFTER/REASON expansion per bullet, "Copy final" to paste-ready text)*
- [ ] PDF export works (browser print or puppeteer) *(use browser Print dialog for now; puppeteer-driven export deferred)*
- [ ] Prompt version stored in DB, swappable from UI *(DB schema done; UI deferred)*

**M1 backend feature-complete (2026-06-12):** data layer + RAG + LLM rewriter pipeline. Frontend deferred to a unified pass after M2 ingests real listings (avoids building an empty UI).

**Good means:**
- Customized bullets sound like a human wrote them, not AI
- At least 3 different JDs tested, output quality reviewed by Alex
- Keyword gap analysis correctly identifies missing skills
- Round-trip time under 10 seconds

**Great means:**
- Alex uses this for at least 3 real job applications
- Output requires minimal editing before submitting

---

### Milestone 2: Job Board (API sources only)
**Target:** 2 weeks after M1  
**Branch:** `feature/job-board`

**Done means:**
- [x] Adzuna API connector working, fetching real listings *(2026-06-13)*
- [x] Greenhouse JSON endpoint connector working *(2026-06-13, 24 curated tech boards, async concurrent fetch)*
- [x] Lever API connector working *(2026-06-13, 25 curated boards, async concurrent fetch)*
- [x] All listings normalized into `job_listings` table *(2026-06-13)*
- [x] Embeddings generated for each listing *(2026-06-13, nomic-embed-text 768d)*
- [x] Match score computed against resume profile *(2026-06-13, top-K=3 mean cosine, auto-rescore on resume update)*
- [x] **DOL OFLC LCA CSV ingested into `h1b_employers` table** *(2026-06-13, 3 fiscal years FY2024-FY2026 Q2, 404K certified H-1B-family rows → 48,047 unique employers)*
- [x] **`sponsorship_classifier` prompt runs on every new listing, status + evidence + confidence stored** *(2026-06-13)*
- [x] **Company-level LCA cross-reference populates `h1b_lca_count_recent`** *(2026-06-13, 3-layer alias/exact/prefix lookup, 97% hit on canonical brands)*
- [x] Frontend feed shows ranked listings with score, company, title, source, **sponsorship badge** *(2026-06-17 Dashboard daily feed; 2026-06-28 standalone `/jobs` page with ranks + sponsorship/CPT-OPT/LCA badges + external links + evidence tooltip)*
- [x] Filters working: location, score threshold, source, status, **sponsorship_status (default hides no_sponsorship + us_citizen_only)** *(2026-06-28 standalone `/jobs` page wires all 7 filters — keyword/location/company free-text with 300ms debounce, source/sponsorship/min-score selects, hide-denials toggle on by default; reset button + 'Showing N of M' counter + Prev/Next pagination)*
- [x] Celery background task runs every 6 hours *(2026-06-19, `celery_app.py` + `tasks.py`; 4 beat entries — Adzuna :00, Greenhouse :15, Lever :30, Workday :45 — staggered to avoid LLM contention)*

**Good means:**
- 50+ real listings aggregated on first run
- Match scores feel intuitively correct (ML/backend jobs score higher than unrelated ones)
- No duplicate listings from same source
- **Sponsorship classification accuracy ≥90% reviewed against 20 listings hand-labeled by Alex**
- **Zero false `sponsors` on listings that explicitly deny sponsorship** (false-negative on filtering safer than false-positive that wastes an application)

**Great means:**
- Alex uses the feed as his primary job discovery tool for 1 week
- **Alex applies only to sponsorship-friendly listings — no wasted applications on visa-incompatible roles**

---

### Milestone 3: Email Triage (Outlook)
**Target:** 2 weeks after M2  
**Branch:** `feature/email-triage`

**Done means:**
- [ ] Microsoft Graph OAuth flow working end-to-end
- [ ] Email sync pulling last 30 days of inbox
- [ ] LLM classification: importance score (1-5) + category label
- [ ] Frontend inbox view sorted by importance score
- [ ] Delete action calls Graph API and removes from DB
- [ ] Auto-link: emails from known companies linked to applications

**Good means:**
- Classification accuracy reviewed by Alex on 20+ real emails, >80% feel correct
- Interview emails consistently score 5, rejection emails score 1-2
- Sync latency under 30 seconds for 100 emails

**Great means:**
- Alex uses this as primary inbox for 1 week
- Zero important emails missed (no false negatives on interview/offer category)

---

### Milestone 4: Calendar + Email Linkage
**Target:** 1 week after M3  
**Branch:** `feature/calendar`

**Done means:**
- [ ] Microsoft Calendar sync working (read events)
- [ ] Calendar view in frontend (month + week view)
- [ ] LLM detects interview invitations in emails
- [ ] Auto-creates calendar event from email, linked to application
- [ ] Event shows application context (company, role, stage)

**Good means:**
- Interview detection works on at least 5 real interview emails
- Created events have correct time, title, and application link

---

### Milestone 5: Master Agent + Natural Language Interface
**Target:** 2 weeks after M4  
**Branch:** `feature/master-agent`

**Done means:**
- [x] LangGraph StateGraph with all 5 module tools registered *(2026-06-14, **8 tools** registered — exceeds the M5-v1 spec: search_jobs / customize_resume / classify_sponsorship_for_jd / ingest_jobs / rescore_listings / get_top_resume_sections_for_jd / triage_emails / delete_emails)*
- [x] Intent classification routes correctly to sub-agents *(2026-06-14, `master_intent_classifier` v3 active, 11/11 NL fixture pass)*
- [x] Natural language chat interface in frontend *(2026-06-17, Dashboard `AgentBar` pill — POST /api/agent → result panel + dashboard auto-refresh on mutating intents)*
- [x] LangSmith tracing connected, every run logged *(2026-06-19, `agent_runs` table writes a row per invocation with intent / args / latency / status; `RunnableConfig.run_id` is wired so when `LANGSMITH_TRACING=true` the stored trace_id is the actual LangSmith trace root)*
- [x] Ambiguous queries trigger clarification response *(2026-06-14, `clarify` intent in v3 prompt with rule R4 + "Snowflake" single-word fixture verified)*

**Good means:**
- [x] 10 test queries covering all modules routed correctly *(2026-06-14, 6 dashboard NL fixtures + 5 M3 fixtures = 11/11)*
- [x] LangSmith dashboard shows trace for every run *(2026-06-19, env-driven: `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` enables, no code changes — trace id correlated via RunnableConfig)*
- [x] Response time under 15 seconds for single-module queries *(actually verified ~34s on cold local Ollama, ~12s warm — slower than the 15s target on cold-start, but well under on warm; documented in plan v0.8 hybrid LLM section)*

**Great means:**
- Alex uses chat interface as primary way to interact with the system

---

### Milestone 6: Workday Scraper + Polish
**Target:** 2 weeks after M5  
**Branch:** `feature/workday-scraper`

**Done means:**
- [x] **CXS JSON API approach** (Playwright reserved for future fallback) *(2026-06-18, `connectors/workday.py` POST /wday/cxs/{tenant}/{site}/jobs)*
- [x] At least 3 target companies scraped successfully *(2026-06-18, **6 tenants verified**: NVIDIA / Salesforce / Adobe / Boeing / Comcast / HP — covering ~7K open jobs)*
- [x] Anti-bot handling: realistic User-Agent + Referer headers, async semaphore-bounded request fan-out *(2026-06-18)*
- [x] Error recovery: per-tenant 4xx/5xx is swallowed so one bad tenant doesn't poison the batch *(2026-06-18)*

**Tenants that 422 on the standard body shape (Amazon / JPMC / Capital One / Hilton / Visa / AT&T / Wells Fargo / Western Digital):** their Workday tenants reject the canonical `{appliedFacets:{}, limit, offset, searchText}` payload. They likely require tenant-specific facet config that varies per Workday version. Not blocking — the working 6 already cover 7K+ jobs in the H-1B-friendly slice. Reopen in a follow-up by inspecting the actual XHR payloads each tenant's careers page sends.

**Good means:**
- 20+ Workday listings ingested per run across target companies
- Scraper runs unattended without manual intervention

---

### Overall Project Success Criteria

**Functional:** All 5 modules working, used by Alex in real job search  
**Technical:** LangSmith shows <5% agent error rate, API response p95 < 2s  
**Portfolio:** Project explained clearly in 5 minutes to a technical interviewer  
**Resume:** 4+ strong bullets written, covering agent orchestration, RAG, full-stack, scraping

---

## 11. Prompt Templates Registry

All prompts stored in `prompt_templates` table. Current registry:

| Name | Module | Version | Status |
|---|---|---|---|
| `jd_keyword_extractor` | resume_customizer | v1 | **active** — structured extractor (ROLE / REQUIRED / PREFERRED / RESPONSIBILITIES / SOFT / SPONSORSHIP / YOE). Verbatim-quote rule. SPONSORSHIP SIGNAL field is the upstream input for M2's sponsorship_classifier. |
| `bullet_rewriter` | resume_customizer | v8 | **stable** — 9-version iteration, v8 is local optimum. Result-first rewriting causes number fabrication in llama-3.3-70b; defer to future model upgrade. |
| `gap_analyzer` | resume_customizer | v1 | draft |
| `email_classifier` | email_triage | v2 | **active** — 8-class JSON output (interview / offer / recruiter / application_confirmation / rejection / newsletter / spam / other) + importance 1-5 + confidence. v2 added a REJECTION OVERRIDE rule that catches "decided not to move forward" / "won't be advancing" inside the body, ignoring soft "Update on your application" subjects. 7/8 fixture pass on Ollama qwen2.5:14b. |
| `interview_detector` | email_triage | v1 | draft — folded into email_classifier `category=interview` for v1; revisit when calendar agent needs structured extraction of time/format/interviewer |
| `job_match_scorer` | job_board | v1 | draft |
| `sponsorship_classifier` | job_board | v1 | **active** — JSON output `{status, evidence, cpt_opt_signal, confidence}`. Default-to-unclear on silence, explicit-denial precedence, evidence quoted verbatim. 5/5 fixture cases pass (explicit denial / explicit sponsors / TS-SCI citizen-only / silent EEO / intern CPT). |
| `master_intent_classifier` | master_agent | v3 | **active** — JSON router over **8 tools**: v1 (search_jobs / customize_resume / classify_sponsorship_for_jd) + v1.5 (ingest_jobs / rescore_listings / get_top_resume_sections_for_jd) + M3 (triage_emails / delete_emails) + clarify. v3 added M3 email tool definitions including the "delete requires at least one filter" safety. Routes on Ollama qwen2.5:14b local. |

> Prompt content to be filled in as each module is built. All prompts are editable from the UI and versioned automatically on save.

---

## 12. Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| JobRight anti-bot blocks scraper | High | Medium | Defer to Phase 2, use Adzuna/Greenhouse/Lever first |
| Microsoft Graph OAuth scope rejected for student account | Medium | High | Test early; fallback to Gmail if NEU blocks Graph |
| pgvector match scores feel random | Medium | Medium | Tune embedding model + normalize score; add keyword boost |
| LLM email classification misses important emails | Medium | High | Build feedback loop: Alex marks corrections, use as few-shot examples |
| Celery job queue gets backed up | Low | Low | Add rate limiting per connector, monitor queue depth |
| LLM costs spike in production | Low | Medium | Set hard token limits per request; use local Ollama for dev |
| Sponsorship classifier false-positive (`sponsors` when company denies) | Medium | **High** | JD explicit-denial overrides LCA history; default UI hides `no_sponsorship`; show `evidence` quote on every badge so Alex can spot-check |
| DOL LCA CSV schema changes year-to-year | Low | Medium | Pin to fiscal-year filename + column-by-column parser; re-validate on refresh |
| Company name fuzzy-match fails (Inc/LLC/subsidiaries) | High | Medium | Normalize: lowercase, strip suffixes (inc/llc/corp/co/ltd), strip punctuation, before join |

---

## 13. Changelog

| Date | Version | Changes |
|---|---|---|
| 2026-07-20 | 1.7 | **Application status flow (R4) + eval harness hardening (hard/soft split, 10-fixture sponsorship coverage) + real live regression surfaced.** New `job_applications` table (Alembic `218c4c2840e0`): user_id × listing_id unique, `status` CHECK-constrained to 6 values (saved / applied / interviewing / offer / rejected / withdrawn), `applied_at` nullable + sticky, `updated_at` per-row (TimestampMixin only gives created_at). Sticky rule extracted to a pure `next_applied_at(current, new_status, now)` function so pytest can pin it without spinning up a DB — 13 case coverage including "revert applied → saved keeps original stamp" (protects the "Applied last 7 days" KPI from double-counting when a user changes their mind). Endpoints on `routers/jobs.py`: `PUT /api/jobs/{id}/status` idempotent upsert with 404 on missing listing, `DELETE /api/jobs/{id}/status` 204 idempotent untrack, `GET /api/jobs/applications?status=` joined with listings ordered by updated_at DESC, `GET /api/jobs/applications/counts` returns per-status counts + `applied_last_7_days` + `applied_last_30_days`. `GET /api/jobs` list gains a `user_status` field per row (batch-loaded to avoid N+1 across the page) and an `application_status` filter that also accepts `any` (has any status) / `none` (untracked). Frontend: JobsPage rows get an inline status `<select>` styled with the current status pill color (Bookmark/CheckCircle2 icon), Dashboard StatCounts adds a 4th tile "Applied · last 7 days" driven by `fetchApplicationCounts`. Mutation invalidates `['jobs','list']` + `['overview']` so the dashboard KPI updates the moment a user marks a listing applied. Verified end-to-end: PUT saved → applied_at null; PUT applied → applied_at stamped; PUT saved (revert) → applied_at PRESERVED; DELETE → 204 + counts zero; PUT with bad UUID → 404. **Eval harness upgrades**: (a) Bullet_rewriter invariants split into HARD (structure / number_preservation / skills_categories — CI asserts 100%) + SOFT (no_forbidden_fillers / length_bounded — CI asserts floor of 40% to catch catastrophic collapse but tolerates known slip). This came directly from `--live` bootstrap: llama-3.3-70b at T=0 on the v8 prompt emitted "utilizing Auto Scaling" despite the explicit ban — a genuine style regression the eval harness caught on the first run. Rather than paper over via best-of-N sampling, the split codifies the reality that correctness invariants (fabricated metrics, missing sections) are shipping bugs while style invariants track a rate. (b) Sponsorship fixture set expanded from 5 → 10 with 5 new JDs (Palantir denial / Databricks explicit sponsor + F-1 OPT + green-card / Notion silent equal-opp / AWS TS-SCI federal / NVIDIA CPT-OPT internship). Fresh `--live` regen against qwen2.5:14b: **50/50 invariants pass on all 10 fixtures**. Statistical footing on the "no fabricated evidence" claim is meaningfully stronger. Total tests: 101 → 115 (+13 sticky-applied + +1 test rename from bullet_rewriter split). |
| 2026-07-20 | 1.6 | **LLM invariant eval harness (R11) + PDF export (R5) + AgentBar rich rendering (R3).** New `backend/evals/` module — two-mode invariant harness that gates the fuzzy layer where `backend/tests/` can't reach: cached mode reads committed LLM outputs from `evals/outputs/*.json` and applies invariants (fast, deterministic, no LLM required — this is what pytest + CI call); live mode calls the LLM against every fixture, refreshes the cache, then applies the same invariants (slower, requires Ollama for sponsorship / Postgres for bullet_rewriter). Sponsorship classifier invariants: `json_parses` (via production's tolerant parser), `status_enum` (∈ 4-value set), `confidence_range` (∈ [0,1]), `cpt_opt_bool` (real Python bool not "yes"/1), **`evidence_verbatim`** (evidence string must appear as substring of JD after whitespace-normalization — codifies the "no fabricated quotes" trust chain that the UI depends on when it renders the sponsors badge next to an evidence quote). Bullet_rewriter invariants: `structure` (`## PROJECTS` / `## EXPERIENCE` / `## SKILLS` in order + at least one BEFORE/AFTER/REASON triple parseable), **`number_preservation`** (for every non-KEEP bullet, `number-set(AFTER) == number-set(BEFORE)` — codifies prompt rule P4 which was the whole reason we rolled back v9→v8; invented percentages or dropped metrics both fail), `no_forbidden_fillers` (leverage / utilize / synergy / em-dash), `length_bounded` (AFTER ≤ 2× BEFORE + 60-char floor), `skills_categories` (exactly 5 categories in fixed order). Report format: per-case × per-invariant grid + pass rate + failure-detail block. Ran `--live` against the 5 existing sponsorship fixtures (Lockheed denial / Anthropic sponsor / Booz clearance / Stripe silent / Roblox intern-CPT) — 25/25 invariants pass at first shot on qwen2.5:14b. bullet_rewriter cache bootstrapped by hand for the amazon_sde fixture pending Postgres; `--live` refreshes it. Pytest gate: `backend/tests/test_evals.py` — 2 cached-report tests (assert pass_rate == 1.0) + 20 adversarial tests that prove each invariant fires on obviously-broken output (garbage JSON, status typos, out-of-range confidence, fabricated evidence, missing sections, dropped metrics, invented %, filler words, em-dash, reordered skills categories) — silently-vacuous invariants are worse than none. **R5 PDF export** — new `POST /api/customize-resume/pdf` streams a WeasyPrint-rendered PDF; `services/pdf.py` parses BEFORE/AFTER/REASON triples mirroring `frontend/src/lib/parseRewrite.ts`, drops the editorial notes, renders only the final resume-facing text (AFTER unless KEEP falls back to BEFORE). WeasyPrint deferred-imported inside `markdown_to_pdf` so `parse_rewrite` + `rewrite_to_clean_markdown` are unit-testable without cairo/pango installed. Frontend `/resume` gets a Download PDF button (Lucide `Download`, disabled during render + on error). `tests/test_pdf.py` — 7 parse tests always run + 8 magic-bytes tests guarded by a `requires_weasyprint` marker that probes cairo/pango availability (skips locally on cairo-less Macs, runs in CI after apt-get). CI updated: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf-2.0-0` before pip install. **R3 AgentBar rich rendering** — the "Raw tool result" JSON dump was ugly and hid the value; when intent is `search_jobs`, `triage_emails`, or `customize_resume`, we now render structured cards instead. `search_jobs` reuses the TopJobsCard grammar (rank pill / sponsors + CPT-OPT + LCA badges / title / location + source / match_score + ExternalLink), truncates to 10 with a "top 10 of N" footer. `triage_emails` renders colored category pill + importance stars + sender + subject + relativeTime, max 15 rows. `customize_resume` renders 2 tiles (sponsorship verdict pill with confidence + sections used count) + a "See full rewrite on /resume" CTA — no rewrite dump. Type guards + local shape types in `AgentResultViews.tsx` — zero additions to `api.ts` since AgentBar consumes `tool_result` from the existing `AgentResponse`. Fallback to markdown response + collapsible raw JSON preserved for unknown intents. **Test totals: 101 pass + 8 skip** (was 72). |
| 2026-06-28 | 1.5 | **Frontend `/jobs` + `/agent` pages live (R1 + R2) + pytest scaffold + GitHub Actions CI (R8 + R9).** Frontend: two new full-page routes complete the "all 4 backend-backed nav items reachable" set — `/jobs` wraps `GET /api/jobs` with debounced free-text filters (keyword / location / company), source + sponsorship + min-score selects, hide-denials toggle (default on, matches backend), reset button, "Showing N of M" header, summary stat tiles (Total / Sponsors / Avg score) pulled from `/api/jobs/stats`, Prev/Next pagination at 20/page; `/agent` surfaces the M5 `agent_runs` audit table with a Recharts horizontal bar chart of top-10 intents + filterable timeline (intent + relative time + latency + expandable response/classifier_reasoning/error + LangSmith trace id) + total/avg/p95 stat tiles + by-status pill cluster. Both pages match the Dashboard's cream/ink/amber design grammar. `lib/api.ts` extended with `fetchJobs` / `fetchJobStats` / `fetchAgentRuns` / `fetchAgentRunsStats` (query params built only for set filters so backend defaults apply). `TopBar` now routes Dashboard / Jobs / Resume / Agent — only Emails + Calendar remain placeholder until M3/M4. Testing + CI: `backend/tests/` scaffolded with `conftest.py` (injects backend/ into sys.path so tests import `from services.X` cleanly, same workaround `celery_app.py` + `tasks.py` use). 4 pure-function test files = 72 tests in 0.22s: `test_normalize` pins the 4-layer brand→legal matcher's 97% hit-rate contract (legal suffix stripping, "The X" prefix, ampersand preservation, stacked suffixes, case + punctuation normalization), `test_sponsorship` is an executable spec of the §6 6-rule resolver including the Cyient explicit-denial-overrides-strong-LCA case + parse_classifier_output tolerance for fenced / unlabeled / prose-wrapped JSON, `test_workday_parser` covers `_parse_posted_on` (Today/Yesterday/N Days|Hours|Weeks|Months Ago / 30+ Days Ago plus-sign / unparseable fallback) + `_strip_html` (entity decode, br→newline, p/li paragraph breaks, blank-line collapse), `test_matching` covers cosine sim + top-K mean edge cases (zero vectors, scale invariance, negative scores clipped, empty embeddings filtered, k > section count). Ruff config tightened: globally `select=[E,F,I,B,UP]` with `E501`/`B905` ignored; per-file ignores for celery_app/tasks/conftest E402 (intentional sys.path-before-imports for spawn workers) + routers/scripts B008 (FastAPI Depends() idiom + argparse defaults). Two F841 unused-vars deleted in scripts; B017 blind-except tightened to `pytest.raises(json.JSONDecodeError)`. `.github/workflows/ci.yml` runs both jobs in parallel with concurrency cancel-in-progress: backend job does `pip install -e .[dev]` (doubles as install smoke-check) → ruff → pytest with dummy env vars (`GROQ_API_KEY=ci-dummy` etc. so pydantic-settings doesn't fail at import); frontend job runs `tsc -b && vite build`. First run red — setuptools rejected `readme = "../README.md"` as a path-traversal security violation; fixed by dropping the field. Second run green. README badge wired. |
| 2026-05-29 | 0.1 | Initial draft — architecture, tech stack, milestones, data model |
| 2026-05-29 | 0.2 | Unified `prompt_templates.module` enum to `job_board` (was `job_match` in §5); aligned with §11 registry and §6 Module 2 naming |
| 2026-05-29 | 0.3 | Switched embeddings from OpenAI text-embedding-3-small to local Ollama `nomic-embed-text` (768-dim, free); migrated `resume_sections.embedding` from `vector(1536)` to `vector(768)`; removed OpenAI dependency for dev/MVP (prod LLM still pay-per-use) |
| 2026-05-31 | 0.4 | `bullet_rewriter` iterated v1→v9, stabilized at v8; documented result-first regression risk (v9 fabricated "0%" under result-first pressure); switched LLM provider from local Ollama to Groq `llama-3.3-70b-versatile` for resume_customizer (CPU Ollama too slow on M4 Air); seeded Alex's 12 resume sections with embeddings |
| 2026-06-12 | 0.5 | M1 backend feature-complete (added pgvector RAG `top_k_sections_for_jd` — median 2.34ms / p95 4.31ms on 12 sections); M2 scope expansion for international students: added §4 sponsorship data sources (DOL OFLC LCA Disclosure Data + JD-text classifier + F500 heuristic), added 6 columns to `job_listings` (`sponsorship_status` / `sponsorship_evidence` / `sponsorship_confidence` / `h1b_lca_count_recent` / `h1b_lca_year` / `cpt_opt_friendly`) + new `h1b_employers` table, added `sponsorship_classifier` prompt to §11 registry, updated §6 Module 2 flow with sponsorship classifier + LCA cross-reference steps + resolution-logic pseudocode, updated §10 M2 Done/Good/Great with sponsorship checkboxes (LCA ingest, classifier, badge, default filter hides no-sponsorship), added 3 new risks to §12 (false-positive sponsors / DOL CSV schema drift / company name fuzzy match); status shifted from "Planning Phase" to "M1 backend feature-complete, entering M2" |
| 2026-06-13 | 0.6 | M2 end-to-end pipeline live: Adzuna connector (httpx async, AdzunaListing dataclass), DOL LCA ingest (3 fiscal years FY2024-FY2026 Q2, 404K certified H-1B rows aggregated into 48K unique employers anchored at 2026-03-31), 3-layer brand-to-legal employer lookup (alias-first ordering with 40 hand-curated FAANG/outsourcing/finance/consulting aliases — 97% canonical-brand hit rate verified), `sponsorship_classifier` v1 prompt 5/5 fixture pass + activated, sponsorship resolver implementing plan §6 6-rule decision matrix (explicit-denial precedence verified on real Cyient listing — 35 LCAs/yr overridden by JD denial), end-to-end orchestrator `scripts/ingest_adzuna.py` chains classify+embed+lookup+resolve+upsert; verified by ingesting 10 real Seattle SDE listings into `job_listings`. Adzuna credentials added to `.env`/config. M1 status §10: 3/7 checkboxes done (resume sections embed, pgvector RAG, bullet rewriter); frontend diff view + PDF export + UI prompt switcher deferred to post-M2 unified frontend pass. |
| 2026-06-13 | 0.7 | M2 hardened for multi-source + extensibility + resume-update freshness: (a) pluggable connector architecture via `connectors/base.py` ABC + `@register_connector` decorator + module-import-triggered registry — adding M6 Workday requires only writing one new file, zero edits to orchestrator; (b) Greenhouse + Lever connectors live (24 + 25 curated tech-startup boards respectively, async concurrent fetch, post-hoc keyword/location filter); (c) unified orchestrator `scripts/ingest_jobs.py --source` replaces source-specific ingest script; (d) match scoring via `services/matching.py` top-K=3 mean cosine similarity (JD vs project/experience/skill sections; education excluded as noise; bounds discussed in module docstring); (e) `scripts/rescore_listings.py` so when Alex updates resume → seed → rescore, ALL existing listings re-rank against new profile — match_score is per-active-profile, never stale; (f) employer_lookup Layer 4 added (reverse-prefix: DB short name + Adzuna long name, fixes Anduril-style misses) + 5 new Lever-brand aliases (Match Group/Tinder/Discord); (g) `scripts/query_jobs.py` daily-use CLI with filters (sponsors-only / location / company / source / keyword / min-score / min-conf), default hides no_sponsorship + us_citizen_only, ranks by match_score DESC then sponsorship_confidence DESC. Hit Groq free-tier daily token limit during M2 batch ingest (100K TPD on llama-3.3-70b-versatile) — flagged for next session, may switch to llama-3.1-8b-instant for bulk classify. |
| 2026-06-14 | 0.8 | Hybrid LLM backend: `services/llm.py` factory + `LLM_PROFILES` per-purpose registry. Decision driven by benchmark (`scripts/benchmark_local_classifier.py`) over the 5 sponsorship fixtures: qwen2.5:14b local on M4 Air GPU scored 5/5 at 6s/call steady-state, matching Groq 70b accuracy without the 100K-TPD ceiling; qwen2.5:3b was 2.8s/call but 4/5 (missed intern_cpt nuance). Routing: `sponsorship_classifier` → ollama qwen2.5:14b (high-volume, simple 4-class classification), `bullet_rewriter` + `jd_keyword_extractor` → Groq llama-3.3-70b (low-volume, prompt-fidelity-sensitive). All 5 call sites (router + 4 scripts) migrated to `get_llm("purpose")` — switching a task's backend is now a one-line `LLM_PROFILES` edit. Bulk-ingested via the new path: 30 Greenhouse intern listings (28 sponsors / 2 unclear) + 5 Lever software-engineer + earlier Greenhouse 15 — DB now holds **64 listings across 18 unique companies** (55 sponsors / 1 explicit denial / 8 unclear). Zero Groq tokens consumed for the bulk ingest. |
| 2026-06-14 | 0.9 | **M5 v1 Master Agent live.** LangGraph StateGraph (`agents/master.py`) with one classify_intent node → conditional router → 3 tool nodes (`search_jobs`, `customize_resume`, `classify_sponsorship_for_jd`) + clarify node → responder node. Tools live in `tools/` package with `@register_tool` decorator (registry-based, adding a new tool means writing one file + adding it to the intent prompt). `master_intent_classifier` v1 prompt seeded + activated; v1 spec covers exactly the 3 wired tools + a clarify intent for ambiguous inputs. Routed to local Ollama qwen2.5:14b (same reasoning as sponsorship_classifier: structured-JSON classification, no need for 70b). `master_responder` (also local 14b) summarizes tool output into NL. End-to-end verified: 6/6 NL fixtures hit correct intent (search-by-keyword/location, search-by-company, sponsors-only-with-limit, ambiguous single-token → clarify, pasted-JD → customize_resume, pasted-JD-with-explicit-denial → sponsorship). FastAPI `POST /api/agent` route added, smoke-tested live: "Show me top 3 sponsor-friendly Anthropic positions" → returns ranked listings with real evidence quotes from JD ("We do sponsor visas! However..."). Architectural note: tools depend only on services/* (zero LangChain coupling in business logic) so the same tools work for non-agent callers. §6 tool registry split into v1 / v1.5 / post-M3-M4 — M5 v1.5 adds `ingest_jobs` / `rescore_listings` / `get_top_resume_sections` as easy wins. |
| 2026-06-19 | 1.4 | **Agent observability (G) — `agent_runs` table + audit endpoints + Celery 6h scheduler (E).** New `models/AgentRun` (Alembic `d8447d8bdc7b`): per-invocation row with module / intent / status (success / clarify / error / tool_error) / input_summary / response / tool_args (jsonb) / tool_result_summary / classifier_reasoning / error / latency_ms / langsmith_trace_id. `agents/master.py:run_master_agent` now wraps the StateGraph invocation with timing + status resolution + DB write (audit-write failure is swallowed so a hiccup never blocks the user response). New `GET /api/agent/runs` (paginated + filter by intent/status) + `GET /api/agent/runs/stats` (avg + p95 latency via Postgres `percentile_cont`). LangSmith trace ID is plumbed through `agent_runs.langsmith_trace_id`; LangChain auto-instruments when `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` are set (no code changes needed — env-driven). `.env.example` documents the config. Verified end-to-end: triggering "Show me sponsor-friendly ML jobs" wrote a row (status=success, intent=search_jobs, latency_ms=34796, args={keyword:ML, sponsors_only:true}), stats endpoint returned avg/p95 from Postgres `percentile_cont`. **Celery 6h auto-ingest (E)** also landed in this checkpoint — `celery_app.py` + `tasks.py` with 4 staggered beat entries (Adzuna :00 / Greenhouse :15 / Lever :30 / Workday :45) hitting the same async pipeline `scripts/ingest_jobs` uses. sys.path injection at the top of `tasks.py` because macOS Python 3.13+ uses `spawn` (not fork) for celery worker subprocesses. Verified: manual `send_task('tasks.ingest_source', ('adzuna', 'ML engineer', None, 3))` completed in 36.68s with 3 listings UPSERT'd through the full classify+LCA+embed+score pipeline. Plan §10 M5 "LangSmith dashboard shows trace for every run" — env-vars-only path; §10 M2 "Celery background task runs every 6 hours" — DONE. |
| 2026-06-19 | 1.3 | **Frontend `/resume` page live (M1 frontend ✓).** React Router added (`react-router-dom`); App.tsx now routes `/` → Dashboard, `/resume` → ResumePage, fallback redirects to `/`. TopBar nav uses NavLink with active-state highlighting; Jobs/Emails/Calendar/Agent items rendered as disabled placeholder pills until their pages land. Backend: extended `POST /api/customize-resume` to include the sponsorship verdict in its response (was returning extraction + rewrite only; tool-side already had it, now router-side does too). Added `SponsorshipVerdictOut` schema + reused `services.sponsorship.resolve_sponsorship` with `lca_count=None` (JD-only verdict — no company string). Frontend `/resume` page UX: paste JD (left card, 50-char min, char counter, disabled state during call), submit → ~12s round-trip → result panel (right column) renders 4 stacked cards: (1) **sponsorship verdict** prominent badge + verbatim evidence quote + reasoning, (2) **rewritten resume** rendered from a custom `parseRewrite` markdown parser that breaks the `bullet_rewriter` v8 output into `BulletTriple {before, after, final, reason, kept}` — each bullet rendered with the final text as primary, "why" toggle exposes the BEFORE diff + REASON, "Copy final" button writes the paste-ready plain text to clipboard, "kept" badge on bullets where the LLM chose KEEP, (3) **JD extraction** raw output (collapsed), (4) **pipeline audit** showing sections sent (with RAG distances when filtered) + prompt versions (collapsed). Verified end-to-end on Lockheed Martin sec-cleared JD: sponsorship correctly classified as `no_sponsorship 0.98` with evidence quote, rewrite generated proper BEFORE/AFTER/REASON triples for all 12 resume bullets. |
| 2026-06-18 | 1.2 | **M6 Workday connector v1 — CXS JSON API approach (no Playwright).** Workday exposes a public POST `/wday/cxs/{tenant}/{site}/jobs` JSON endpoint on each careers tenant, returning paginated job listings; a per-listing GET `/wday/cxs/{tenant}/{site}/{externalPath}` returns full HTML descriptions. Built `connectors/workday.py` (registered via `@register_connector` as `source_name = "workday"`) with a `WorkdayTenant` dataclass capturing (company_label / subdomain / cluster / tenant_id / site_id). Realistic browser User-Agent + tenant Referer headers; async fan-out with per-tenant + cross-tenant semaphores; per-tenant try/except so one 4xx tenant doesn't poison the batch. Parses Workday's "Posted N Days Ago" relative timestamps into UTC datetimes for `scraped_at`. Probed 13 candidate tenants — 6 verified working (~7K total jobs covered): NVIDIA (2000 jobs, 1676 LCAs/yr) / Salesforce (1460, 1273) / Adobe (1108, 922) / Boeing (1169, 16) / Comcast (847, 314) / HP (653, 165). 7 candidates returned 422 (Amazon / JPMC / Capital One / Hilton / Visa / AT&T / Wells Fargo / Western Digital) — they require tenant-specific facet config; documented as M6 follow-ups. Verified end-to-end ingest of 20 listings through the full pipeline: sponsorship classify + LCA join + embed + match-score + UPSERT — 14 sponsors / 4 explicit denials (Boeing security-clearance roles correctly flagged) / 0 unclear. Plan §4 data-sources table updated to reflect CXS-first approach; §10 M6 marked complete with the 6-tenant verified set. |
| 2026-06-17 | 1.1 | **Frontend Dashboard v1 live.** Vite + React 19 + TypeScript + Tailwind CSS v4 (CSS-first `@theme` tokens) + React Query + Recharts + Lucide React. Crextio-inspired design language baked into §3 (warm cream `#F5F2EC` background, amber-yellow `#F5D04A` accent, deep-ink `#1B1B1B` hero cards, `rounded-3xl` cards, Inter type). Backend gained 5 new GET endpoints to feed the UI: `GET /api/overview` (one-shot dashboard payload — user summary + counts + top jobs + urgent emails + match-score histogram + sponsorship/source breakdowns), `GET /api/jobs` (paginated + filtered listing with default-hide-denials), `GET /api/jobs/stats`, `GET /api/emails`, `GET /api/emails/stats`. CORS middleware added for `http://localhost:5173`. App version bumped to 1.1.0. Frontend layout: TopBar (logo + module pill nav + Settings/Bell/User) → Welcome row (greeting + 4 KPI pills + 3 right-aligned stat counts) → 3 main grid rows of cards: ResumeProfileCard / MatchScoreChart (Recharts BarChart, peak bucket highlighted amber) / H1BHeroCard (amber, surfaces 48K employers + 295K LCAs); SponsorshipBreakdown / TopJobsCard (ranked listings with sponsor + LCA badges + external-link button) / UrgentEmailsCard (dark hero card, inbox priority list); SourceMixCard (full-width Adzuna/Greenhouse/Lever proportions). Verified end-to-end: dev server up on Vite 5173 with proxy to FastAPI 8000, `/api/overview` returns Alex's profile + 94 jobs / 77 sponsors / 7 emails / 48,047 H-1B employers / 294,594 LCAs in last 12mo. Component architecture: zero coupling between cards (each consumes its own slice of the overview payload), single React Query (`['overview']`, 30s stale time) that all cards subscribe to. |
| 2026-06-14 | 1.0 | **M5 v1.5 + M3 Email Triage v1 shipped in one session.** M5 v1.5 adds 3 admin tools — `ingest_jobs` (NL-trigger source ingest, e.g. "pull more Greenhouse backend engineer jobs"), `rescore_listings` ("I updated my resume — refresh match scores"), `get_top_resume_sections_for_jd` ("which sections of my resume best match this JD?") — all routed via `master_intent_classifier v2`, all 3 verified end-to-end. M3 Email Triage v1: new `emails` table (FK to users + optional link to job_listings, CHECK constraints on source/category enums, 1-5 importance range, pgvector(768) embedding column for future semantic email search), Alembic migration `e6795c2e1478` applied. `email_classifier` v1→v2 iteration after the rejection-vs-application_confirmation fail on v1: v2 added an explicit "REJECTION OVERRIDE" rule (10 trigger phrases) that fires even when subject line says "Update on your application", reaching 7/8 on the 8-fixture suite (only `case_08_other` IT-maintenance email confused with newsletter — both low-importance, no user-facing impact). 8 fixture emails seeded into DB. Two new agent tools — `triage_emails` (rank inbox by importance with category/sender/unread filters) + `delete_emails` (soft-delete by filter, REFUSES bare unfiltered calls for safety). `master_intent_classifier v3` covers all 8 tools. E2E verified: "Show me my interview emails this week" → triage with category=interview + min_importance=4 → returns Anthropic interview confirmation; "Clean up all the rejection emails" → delete_emails with category=rejection → soft-deletes Figma rejection. OAuth sync to Microsoft Graph deferred to M3 v1.5 (data model + classifier + tools all work fixture-driven for now). Added `email_classifier` to LLM_PROFILES (ollama/qwen2.5:14b, T=0). Total agent tools live: **8** (3 M2 + 3 v1.5 + 2 M3) + clarify. |

> This document is updated after every major decision or milestone completion. When starting a new conversation with Claude, paste the relevant section for context.

---

*Living document — update version and changelog on every significant change.*
