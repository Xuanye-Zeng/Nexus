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
