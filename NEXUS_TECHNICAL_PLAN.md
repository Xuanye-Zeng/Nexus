# Nexus — AI-Powered Personal Job Search Assistant
## Technical Plan & Living Document

> **Version:** 0.6  
> **Last Updated:** 2026-06-13  
> **Owner:** Xuanye (Alex) Zeng  
> **Status:** M1 backend feature-complete; M2 end-to-end pipeline live (Adzuna + LCA + sponsorship verdict)

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
| Calendar UI | FullCalendar.io | Production-grade calendar component |
| Build | Vite | Fast dev server |

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
| Workday | Playwright scraper | Covers Amazon, Microsoft, Apple |
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

**Tool registry:**
```python
tools = [
    search_jobs_tool,
    get_job_detail_tool,
    match_resume_to_jd_tool,
    customize_resume_tool,
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

**CI (on every PR to develop):**
```yaml
- Lint: ruff (Python), eslint (TypeScript)
- Type check: mypy (Python), tsc (TypeScript)
- Unit tests: pytest (backend), vitest (frontend)
- Integration tests: pytest with test DB
- Docker build check
```

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
- [ ] JD input → keyword extraction working *(`jd_keyword_extractor` prompt pending)*
- [x] pgvector similarity search returning relevant sections *(2026-06-12, `top_k_sections_for_jd`, median 2.34ms / p95 4.31ms)*
- [x] LLM rewriting bullets using JD language *(2026-05-31, `bullet_rewriter` v8 stable, 1% bullet fail rate)*
- [ ] Frontend diff view shows original vs customized side-by-side *(deferred to post-M2 unified frontend pass)*
- [ ] PDF export works (browser print or puppeteer) *(deferred to post-M2)*
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
- [ ] Greenhouse JSON endpoint connector working
- [ ] Lever API connector working
- [x] All listings normalized into `job_listings` table *(2026-06-13)*
- [x] Embeddings generated for each listing *(2026-06-13, nomic-embed-text 768d)*
- [ ] Match score computed against resume profile *(field present, scoring pass deferred)*
- [x] **DOL OFLC LCA CSV ingested into `h1b_employers` table** *(2026-06-13, 3 fiscal years FY2024-FY2026 Q2, 404K certified H-1B-family rows → 48,047 unique employers)*
- [x] **`sponsorship_classifier` prompt runs on every new listing, status + evidence + confidence stored** *(2026-06-13)*
- [x] **Company-level LCA cross-reference populates `h1b_lca_count_recent`** *(2026-06-13, 3-layer alias/exact/prefix lookup, 97% hit on canonical brands)*
- [ ] Frontend feed shows ranked listings with score, company, title, source, **sponsorship badge** *(deferred to post-M2 frontend pass)*
- [ ] Filters working: location, score threshold, source, status, **sponsorship_status (default hides no_sponsorship + us_citizen_only)** *(deferred, schema supports)*
- [ ] Celery background task runs every 6 hours *(manual ingest works, scheduler deferred)*

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
- [ ] LangGraph StateGraph with all 5 module tools registered
- [ ] Intent classification routes correctly to sub-agents
- [ ] Natural language chat interface in frontend
- [ ] LangSmith tracing connected, every run logged
- [ ] Ambiguous queries trigger clarification response

**Good means:**
- 10 test queries covering all modules routed correctly
- LangSmith dashboard shows trace for every run
- Response time under 15 seconds for single-module queries

**Great means:**
- Alex uses chat interface as primary way to interact with the system

---

### Milestone 6: Workday Scraper + Polish
**Target:** 2 weeks after M5  
**Branch:** `feature/workday-scraper`

**Done means:**
- [ ] Playwright scraper handles Workday login/session
- [ ] At least 3 target companies scraped successfully (Amazon, Microsoft, one more)
- [ ] Anti-bot handling: random delays, realistic headers
- [ ] Error recovery: scraper doesn't crash on single page failure

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
| `email_classifier` | email_triage | v1 | draft |
| `interview_detector` | email_triage | v1 | draft |
| `job_match_scorer` | job_board | v1 | draft |
| `sponsorship_classifier` | job_board | v1 | **active** — JSON output `{status, evidence, cpt_opt_signal, confidence}`. Default-to-unclear on silence, explicit-denial precedence, evidence quoted verbatim. 5/5 fixture cases pass (explicit denial / explicit sponsors / TS-SCI citizen-only / silent EEO / intern CPT). |
| `master_intent_classifier` | master_agent | v1 | draft |

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
| 2026-05-29 | 0.1 | Initial draft — architecture, tech stack, milestones, data model |
| 2026-05-29 | 0.2 | Unified `prompt_templates.module` enum to `job_board` (was `job_match` in §5); aligned with §11 registry and §6 Module 2 naming |
| 2026-05-29 | 0.3 | Switched embeddings from OpenAI text-embedding-3-small to local Ollama `nomic-embed-text` (768-dim, free); migrated `resume_sections.embedding` from `vector(1536)` to `vector(768)`; removed OpenAI dependency for dev/MVP (prod LLM still pay-per-use) |
| 2026-05-31 | 0.4 | `bullet_rewriter` iterated v1→v9, stabilized at v8; documented result-first regression risk (v9 fabricated "0%" under result-first pressure); switched LLM provider from local Ollama to Groq `llama-3.3-70b-versatile` for resume_customizer (CPU Ollama too slow on M4 Air); seeded Alex's 12 resume sections with embeddings |
| 2026-06-12 | 0.5 | M1 backend feature-complete (added pgvector RAG `top_k_sections_for_jd` — median 2.34ms / p95 4.31ms on 12 sections); M2 scope expansion for international students: added §4 sponsorship data sources (DOL OFLC LCA Disclosure Data + JD-text classifier + F500 heuristic), added 6 columns to `job_listings` (`sponsorship_status` / `sponsorship_evidence` / `sponsorship_confidence` / `h1b_lca_count_recent` / `h1b_lca_year` / `cpt_opt_friendly`) + new `h1b_employers` table, added `sponsorship_classifier` prompt to §11 registry, updated §6 Module 2 flow with sponsorship classifier + LCA cross-reference steps + resolution-logic pseudocode, updated §10 M2 Done/Good/Great with sponsorship checkboxes (LCA ingest, classifier, badge, default filter hides no-sponsorship), added 3 new risks to §12 (false-positive sponsors / DOL CSV schema drift / company name fuzzy match); status shifted from "Planning Phase" to "M1 backend feature-complete, entering M2" |
| 2026-06-13 | 0.6 | M2 end-to-end pipeline live: Adzuna connector (httpx async, AdzunaListing dataclass), DOL LCA ingest (3 fiscal years FY2024-FY2026 Q2, 404K certified H-1B rows aggregated into 48K unique employers anchored at 2026-03-31), 3-layer brand-to-legal employer lookup (alias-first ordering with 40 hand-curated FAANG/outsourcing/finance/consulting aliases — 97% canonical-brand hit rate verified), `sponsorship_classifier` v1 prompt 5/5 fixture pass + activated, sponsorship resolver implementing plan §6 6-rule decision matrix (explicit-denial precedence verified on real Cyient listing — 35 LCAs/yr overridden by JD denial), end-to-end orchestrator `scripts/ingest_adzuna.py` chains classify+embed+lookup+resolve+upsert; verified by ingesting 10 real Seattle SDE listings into `job_listings`. Adzuna credentials added to `.env`/config. M1 status §10: 3/7 checkboxes done (resume sections embed, pgvector RAG, bullet rewriter); frontend diff view + PDF export + UI prompt switcher deferred to post-M2 unified frontend pass. |

> This document is updated after every major decision or milestone completion. When starting a new conversation with Claude, paste the relevant section for context.

---

*Living document — update version and changelog on every significant change.*
