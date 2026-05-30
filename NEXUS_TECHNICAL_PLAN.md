# Nexus — AI-Powered Personal Job Search Assistant
## Technical Plan & Living Document

> **Version:** 0.1 — Initial Draft  
> **Last Updated:** 2026-05-29  
> **Owner:** Xuanye (Alex) Zeng  
> **Status:** Planning Phase

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
| Embeddings | text-embedding-3-small (OpenAI) | Cost-efficient, 1536-dim |
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

### LLM / AI
| Service | Usage | Cost |
|---|---|---|
| Ollama (local) | Development & testing | Free |
| OpenAI API | Embeddings (text-embedding-3-small) | ~$0.02/1M tokens |
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
resume_sections (id, profile_id, section_type, content_json, embedding vector(1536))
  -- section_type: 'project' | 'experience' | 'skill' | 'education'

-- Job listings
job_listings (
  id, source, source_id, company, title, location, 
  description_raw, description_clean, 
  match_score float, embedding vector(1536),
  status, -- 'new' | 'saved' | 'applied' | 'rejected' | 'interviewing'
  scraped_at, expires_at
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
  module, -- 'resume_customizer' | 'email_triage' | 'job_match' | 'master_agent'
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
**What it does:** Aggregates listings from multiple sources, scores each against your resume, displays ranked feed.

**Flow:**
1. Celery background task runs scrapers on schedule (every 6hrs)
2. Each connector (Adzuna, Greenhouse, Lever, Workday) fetches listings
3. New listings get embedded and scored against resume profile embedding
4. Frontend displays ranked feed with filters (score, location, company, source)
5. User can save, mark applied, or dismiss

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
- [ ] Resume sections stored in DB with embeddings
- [ ] JD input → keyword extraction working
- [ ] pgvector similarity search returning relevant sections
- [ ] LLM rewriting bullets using JD language
- [ ] Frontend diff view shows original vs customized side-by-side
- [ ] PDF export works (browser print or puppeteer)
- [ ] Prompt version stored in DB, swappable from UI

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
- [ ] Adzuna API connector working, fetching real listings
- [ ] Greenhouse JSON endpoint connector working
- [ ] Lever API connector working
- [ ] All listings normalized into `job_listings` table
- [ ] Embeddings generated for each listing
- [ ] Match score computed against resume profile
- [ ] Frontend feed shows ranked listings with score, company, title, source
- [ ] Filters working: location, score threshold, source, status
- [ ] Celery background task runs every 6 hours

**Good means:**
- 50+ real listings aggregated on first run
- Match scores feel intuitively correct (ML/backend jobs score higher than unrelated ones)
- No duplicate listings from same source

**Great means:**
- Alex uses the feed as his primary job discovery tool for 1 week

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
| `jd_keyword_extractor` | resume_customizer | v1 | draft |
| `bullet_rewriter` | resume_customizer | v1 | draft |
| `gap_analyzer` | resume_customizer | v1 | draft |
| `email_classifier` | email_triage | v1 | draft |
| `interview_detector` | email_triage | v1 | draft |
| `job_match_scorer` | job_board | v1 | draft |
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

---

## 13. Changelog

| Date | Version | Changes |
|---|---|---|
| 2026-05-29 | 0.1 | Initial draft — architecture, tech stack, milestones, data model |

> This document is updated after every major decision or milestone completion. When starting a new conversation with Claude, paste the relevant section for context.

---

*Living document — update version and changelog on every significant change.*
