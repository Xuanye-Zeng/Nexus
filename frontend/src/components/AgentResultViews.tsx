import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  ExternalLink,
  FileText,
  Layers,
  MapPin,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { relativeTime } from '../lib/relativeTime'

// ---- local shapes for tool_result payloads ----
// These deliberately mirror the backend tool return shapes without adding new
// exports to lib/api.ts (per task constraint).

type SponsorshipStatus =
  | 'sponsors'
  | 'no_sponsorship'
  | 'us_citizen_only'
  | 'unclear'

interface SearchJobsListing {
  id: string
  source: string
  company: string
  title: string
  location: string | null
  // backend returns `url`; the task doc references `source_url` — accept either.
  url?: string | null
  source_url?: string | null
  match_score: number | null
  sponsorship_status: SponsorshipStatus | null
  sponsorship_confidence: number | null
  sponsorship_evidence: string | null
  h1b_lca_count_recent: number | null
  cpt_opt_friendly: boolean | null
}

export interface SearchJobsResult {
  count?: number
  filters?: Record<string, unknown>
  listings: SearchJobsListing[]
}

interface TriageEmail {
  id: string
  category: string | null
  importance_score: number | null
  sender_name: string | null
  sender: string | null
  subject: string | null
  received_at: string | null
}

export interface TriageEmailsResult {
  count?: number
  emails: TriageEmail[]
}

export interface CustomizeResumeResult {
  sponsorship: {
    status: SponsorshipStatus
    confidence?: number | null
    evidence?: string | null
    cpt_opt_friendly?: boolean | null
    reasoning?: string | null
  }
  sections_used_count?: number | null
  sections_used?: unknown[] | null
  rewritten_resume?: string | null
}

// ---- type guards ----

export function isSearchJobsResult(x: unknown): x is SearchJobsResult {
  return (
    !!x &&
    typeof x === 'object' &&
    Array.isArray((x as { listings?: unknown }).listings)
  )
}

export function isTriageEmailsResult(x: unknown): x is TriageEmailsResult {
  return (
    !!x &&
    typeof x === 'object' &&
    Array.isArray((x as { emails?: unknown }).emails)
  )
}

export function isCustomizeResumeResult(x: unknown): x is CustomizeResumeResult {
  if (!x || typeof x !== 'object') return false
  const sponsorship = (x as { sponsorship?: unknown }).sponsorship
  return (
    !!sponsorship &&
    typeof sponsorship === 'object' &&
    typeof (sponsorship as { status?: unknown }).status === 'string'
  )
}

// ---- shared style tokens ----

const SOURCE_LABEL: Record<string, string> = {
  adzuna: 'Adzuna',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  workday: 'Workday',
}

// Same visual grammar as JobsPage.tsx sponsorship pills — sponsors are the
// hero amber, explicit denials read as red, unclear stays neutral cream.
const SPONSORSHIP_PILL: Record<SponsorshipStatus, string> = {
  sponsors: 'bg-amber-brand text-ink-900',
  no_sponsorship: 'bg-red-50 text-red-700 border border-red-200',
  us_citizen_only: 'bg-red-50 text-red-700 border border-red-200',
  unclear: 'bg-cream-200 text-ink-700',
}

const SPONSORSHIP_LABEL: Record<SponsorshipStatus, string> = {
  sponsors: 'Sponsors visas',
  no_sponsorship: 'No sponsorship',
  us_citizen_only: 'US citizens only',
  unclear: 'Unclear',
}

const CATEGORY_PILL: Record<string, string> = {
  interview: 'bg-amber-brand text-ink-900',
  offer: 'bg-emerald-100 text-emerald-800',
  rejection: 'bg-red-50 text-red-700 border border-red-200',
  application_confirmation: 'bg-blue-50 text-blue-700 border border-blue-200',
  event: 'bg-purple-50 text-purple-700 border border-purple-200',
  newsletter: 'bg-cream-200 text-ink-500',
  personal: 'bg-cream-100 text-ink-700',
  other: 'bg-cream-100 text-ink-700',
}

function categoryPill(cat: string | null): string {
  if (!cat) return CATEGORY_PILL.other
  return CATEGORY_PILL[cat] ?? CATEGORY_PILL.other
}

function stars(score: number | null): string {
  const n = Math.max(0, Math.min(5, Math.round(score ?? 0)))
  return '★'.repeat(n) + '☆'.repeat(5 - n)
}

// ---- SearchJobsView ----

export function SearchJobsView({ data }: { data: SearchJobsResult }) {
  const rows = data.listings.slice(0, 10)
  if (rows.length === 0) {
    return (
      <div className="mt-4 py-8 text-center text-sm text-ink-500">
        No matches — try widening filters or run{' '}
        <code className="bg-cream-100 px-1 rounded">ingest_jobs</code> first.
      </div>
    )
  }
  return (
    <ul className="mt-4 divide-y divide-cream-200">
      {rows.map((j, i) => {
        const href = j.source_url ?? j.url ?? null
        const sponsorOK =
          j.sponsorship_status === 'sponsors' ||
          (j.sponsorship_status === 'unclear' &&
            (j.h1b_lca_count_recent ?? 0) > 0)
        return (
          <li key={j.id} className="py-3 flex items-start gap-3">
            <div className="h-9 w-9 rounded-xl bg-cream-100 flex items-center justify-center text-xs font-medium text-ink-700 shrink-0 tabular">
              {i + 1}
            </div>

            <div className="flex-1 min-w-0">
              {/* row 1: company + status badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-ink-900 truncate">
                  {j.company}
                </span>
                {sponsorOK && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-amber-brand text-ink-900">
                    sponsors
                  </span>
                )}
                {j.cpt_opt_friendly && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-ink-900 text-amber-soft flex items-center gap-1">
                    <Sparkles className="h-2.5 w-2.5" />
                    CPT/OPT
                  </span>
                )}
                {j.h1b_lca_count_recent != null &&
                  j.h1b_lca_count_recent > 0 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cream-100 text-ink-700">
                      {j.h1b_lca_count_recent} LCAs/yr
                    </span>
                  )}
              </div>

              {/* row 2: title */}
              <div className="text-sm text-ink-700 truncate mt-0.5">
                {j.title}
              </div>

              {/* row 3: location + source */}
              <div className="mt-1 flex items-center gap-3 text-xs text-ink-500 flex-wrap">
                {j.location && (
                  <span className="flex items-center gap-1 min-w-0">
                    <MapPin className="h-3 w-3 shrink-0" />
                    <span className="truncate">{j.location}</span>
                  </span>
                )}
                <span>{SOURCE_LABEL[j.source] ?? j.source}</span>
              </div>
            </div>

            {/* right column: match_score + external link */}
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              <span className="text-sm font-medium tabular text-ink-900">
                {j.match_score != null ? j.match_score.toFixed(2) : '—'}
              </span>
              {href && (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="h-7 w-7 rounded-full bg-cream-100 flex items-center justify-center hover:bg-amber-brand transition-colors"
                  aria-label="Open posting"
                >
                  <ExternalLink className="h-3 w-3 text-ink-700" />
                </a>
              )}
            </div>
          </li>
        )
      })}
      {data.listings.length > 10 && (
        <li className="pt-3 text-xs text-ink-500 text-center">
          Showing top 10 of {data.listings.length} — refine filters to narrow.
        </li>
      )}
    </ul>
  )
}

// ---- TriageEmailsView ----

export function TriageEmailsView({ data }: { data: TriageEmailsResult }) {
  const rows = data.emails.slice(0, 15)
  if (rows.length === 0) {
    return (
      <div className="mt-4 py-8 text-center text-sm text-ink-500">
        Inbox is quiet — no emails matched.
      </div>
    )
  }
  return (
    <ul className="mt-4 divide-y divide-cream-200">
      {rows.map((e) => (
        <li key={e.id} className="py-3 flex items-start gap-3">
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide shrink-0 mt-0.5 ${categoryPill(
              e.category,
            )}`}
          >
            {e.category ?? 'other'}
          </span>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-ink-900 truncate">
                {e.sender_name ?? e.sender ?? '(unknown sender)'}
              </span>
              <span
                className="text-xs text-amber-strong tabular"
                title={`importance ${e.importance_score ?? 0}/5`}
              >
                {stars(e.importance_score)}
              </span>
            </div>
            <div className="text-sm text-ink-700 truncate mt-0.5">
              {e.subject ?? '(no subject)'}
            </div>
          </div>

          <span className="text-xs text-ink-500 shrink-0 mt-1">
            {relativeTime(e.received_at)}
          </span>
        </li>
      ))}
      {data.emails.length > 15 && (
        <li className="pt-3 text-xs text-ink-500 text-center">
          Showing top 15 of {data.emails.length}.
        </li>
      )}
    </ul>
  )
}

// ---- CustomizeResumeView ----

export function CustomizeResumeView({ data }: { data: CustomizeResumeResult }) {
  const status = (data.sponsorship.status ?? 'unclear') as SponsorshipStatus
  const pill = SPONSORSHIP_PILL[status] ?? SPONSORSHIP_PILL.unclear
  const label = SPONSORSHIP_LABEL[status] ?? SPONSORSHIP_LABEL.unclear
  const confidence = data.sponsorship.confidence
  const sectionsCount =
    data.sections_used_count ??
    (Array.isArray(data.sections_used) ? data.sections_used.length : null)

  return (
    <div className="mt-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* tile 1: sponsorship verdict */}
        <div className="rounded-2xl border border-cream-200 bg-cream-50 p-4">
          <div className="flex items-center gap-2 text-xs text-ink-500">
            <ShieldCheck className="h-3.5 w-3.5" />
            Sponsorship verdict
          </div>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span
              className={`text-sm px-3 py-1 rounded-full font-medium uppercase tracking-wide ${pill}`}
            >
              {label}
            </span>
            {data.sponsorship.cpt_opt_friendly && (
              <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-ink-900 text-amber-soft flex items-center gap-1">
                <Sparkles className="h-2.5 w-2.5" />
                CPT/OPT
              </span>
            )}
          </div>
          {confidence != null && (
            <div className="mt-2 text-xs text-ink-500 tabular">
              confidence {(confidence * 100).toFixed(0)}%
            </div>
          )}
        </div>

        {/* tile 2: sections used */}
        <div className="rounded-2xl border border-cream-200 bg-cream-50 p-4">
          <div className="flex items-center gap-2 text-xs text-ink-500">
            <Layers className="h-3.5 w-3.5" />
            Sections used
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="text-3xl font-semibold tabular text-ink-900 leading-none">
              {sectionsCount ?? '—'}
            </span>
            <span className="text-xs text-ink-500">from RAG + always-keep</span>
          </div>
        </div>
      </div>

      <Link
        to="/resume"
        className="mt-4 inline-flex items-center gap-2 text-sm px-4 py-2 rounded-full bg-ink-900 text-white hover:bg-ink-700 transition-colors"
      >
        <FileText className="h-4 w-4" />
        See full rewrite on /resume
        <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}
