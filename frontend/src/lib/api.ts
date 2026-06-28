import axios from 'axios'

// Vite dev proxy routes /api/* to FastAPI at 127.0.0.1:8000; in prod we'd
// resolve via VITE_API_BASE_URL.
const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

export const api = axios.create({ baseURL })

export type SponsorshipStatus =
  | 'sponsors'
  | 'no_sponsorship'
  | 'us_citizen_only'
  | 'unclear'

export type JobSource = 'adzuna' | 'greenhouse' | 'lever' | 'workday'

export interface TopJob {
  id: string
  source: JobSource
  company: string
  title: string
  location: string | null
  match_score: number | null
  sponsorship_status: SponsorshipStatus | null
  sponsorship_confidence: number | null
  h1b_lca_count_recent: number | null
  cpt_opt_friendly: boolean | null
  source_url: string | null
  scraped_at: string | null
}

export interface UrgentEmail {
  id: string
  category: string | null
  importance_score: number | null
  sender_name: string | null
  sender: string | null
  subject: string | null
  received_at: string | null
}

export interface OverviewData {
  user: {
    email: string
    name: string
    resume_version: number | null
    resume_label: string | null
    sections_count: number
  }
  counts: {
    jobs_total: number
    jobs_sponsors: number
    jobs_unique_companies: number
    emails_total: number
    emails_unread: number
    emails_high_importance: number
    h1b_employers_total: number
    h1b_lcas_recent_total: number
  }
  top_jobs: TopJob[]
  urgent_emails: UrgentEmail[]
  match_score_buckets: { label: string; count: number }[]
  sponsorship_breakdown: Record<string, number>
  source_breakdown: Record<string, number>
}

export async function fetchOverview(): Promise<OverviewData> {
  const { data } = await api.get<OverviewData>('/api/overview')
  return data
}

// ---- Resume Customizer (POST /api/customize-resume) ----

export interface SponsorshipVerdict {
  status: SponsorshipStatus
  confidence: number
  evidence: string
  cpt_opt_friendly: boolean
  reasoning: string
}

export interface SectionAudit {
  section_type: string
  label: string
  distance: number | null
  source: 'rag' | 'always_keep'
}

export interface CustomizeResponse {
  jd_extraction: string
  rewritten_resume: string
  sponsorship: SponsorshipVerdict
  sections_used: SectionAudit[]
  prompt_versions: Record<string, number>
}

export async function customizeResume(
  jdText: string,
  topK?: number,
): Promise<CustomizeResponse> {
  const { data } = await api.post<CustomizeResponse>('/api/customize-resume', {
    jd_text: jdText,
    top_k: topK ?? null,
  })
  return data
}

// ---- Master Agent (POST /api/agent) ----

export interface AgentResponse {
  response: string
  intent: string
  tool_args: Record<string, unknown>
  tool_result: unknown
  classifier_reasoning: string
  error: string
}

export async function runAgent(message: string): Promise<AgentResponse> {
  const { data } = await api.post<AgentResponse>('/api/agent', { message })
  return data
}

/** Intents that mutate dashboard data → caller should invalidate ['overview']. */
export const MUTATING_INTENTS = new Set([
  'ingest_jobs',
  'rescore_listings',
  'delete_emails',
])

// ---- Agent runs (GET /api/agent/runs + /stats) ----

export type AgentRunStatus = 'success' | 'clarify' | 'error' | 'tool_error'

export interface AgentRun {
  id: string
  module: string
  intent: string | null
  status: AgentRunStatus
  input_summary: string | null
  response: string | null
  classifier_reasoning: string | null
  error: string | null
  latency_ms: number | null
  langsmith_trace_id: string | null
  created_at: string
}

export interface AgentRunsPage {
  total: number
  items: AgentRun[]
}

export interface AgentRunsStats {
  total: number
  by_intent: Record<string, number>
  by_status: Record<string, number>
  avg_latency_ms: number | null
  p95_latency_ms: number | null
}

export interface AgentRunsQuery {
  intent?: string | null
  status?: AgentRunStatus | null
  limit?: number
  offset?: number
}

export async function fetchAgentRuns(q: AgentRunsQuery = {}): Promise<AgentRunsPage> {
  const params: Record<string, string | number> = {
    limit: q.limit ?? 20,
    offset: q.offset ?? 0,
  }
  if (q.intent) params.intent = q.intent
  if (q.status) params.status = q.status
  const { data } = await api.get<AgentRunsPage>('/api/agent/runs', { params })
  return data
}

export async function fetchAgentRunsStats(): Promise<AgentRunsStats> {
  const { data } = await api.get<AgentRunsStats>('/api/agent/runs/stats')
  return data
}

// ---- Jobs list (GET /api/jobs + /api/jobs/stats) ----

export interface JobRow {
  id: string
  source: string
  company: string
  title: string
  location: string | null
  source_url: string | null
  match_score: number | null
  sponsorship_status: SponsorshipStatus | null
  sponsorship_confidence: number | null
  sponsorship_evidence: string | null
  h1b_lca_count_recent: number | null
  cpt_opt_friendly: boolean | null
}

export interface JobListPage {
  total: number
  items: JobRow[]
}

export interface JobStats {
  total: number
  by_source: Record<string, number>
  by_sponsorship: Record<string, number>
  by_company_top: { company: string; count: number }[]
  avg_match_score: number | null
  avg_match_score_sponsors_only: number | null
}

export interface JobListQuery {
  keyword?: string | null
  location?: string | null
  company?: string | null
  source?: JobSource | null
  sponsorship_status?: SponsorshipStatus | null
  hide_denials?: boolean
  min_score?: number | null
  limit?: number
  offset?: number
}

export async function fetchJobs(q: JobListQuery = {}): Promise<JobListPage> {
  const params: Record<string, string | number | boolean> = {
    limit: q.limit ?? 20,
    offset: q.offset ?? 0,
    hide_denials: q.hide_denials ?? true,
  }
  if (q.keyword) params.keyword = q.keyword
  if (q.location) params.location = q.location
  if (q.company) params.company = q.company
  if (q.source) params.source = q.source
  if (q.sponsorship_status) params.sponsorship_status = q.sponsorship_status
  if (q.min_score != null) params.min_score = q.min_score
  const { data } = await api.get<JobListPage>('/api/jobs', { params })
  return data
}

export async function fetchJobStats(): Promise<JobStats> {
  const { data } = await api.get<JobStats>('/api/jobs/stats')
  return data
}
