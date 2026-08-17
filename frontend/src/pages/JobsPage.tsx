import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bookmark,
  Briefcase,
  Building2,
  CheckCircle2,
  ExternalLink,
  Gauge,
  MapPin,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import {
  clearJobStatus,
  fetchJobStats,
  fetchJobs,
  upsertJobStatus,
  type ApplicationStatus,
  type JobRow,
  type JobSource,
  type SponsorshipStatus,
} from '../lib/api'
import { TopBar } from '../components/TopBar'

const PAGE_SIZE = 20
const DEBOUNCE_MS = 300

const SOURCE_LABEL: Record<string, string> = {
  adzuna: 'Adzuna',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  workday: 'Workday',
}

const SOURCE_OPTIONS: { label: string; value: JobSource | '' }[] = [
  { label: 'All sources', value: '' },
  { label: 'Adzuna', value: 'adzuna' },
  { label: 'Greenhouse', value: 'greenhouse' },
  { label: 'Lever', value: 'lever' },
  { label: 'Workday', value: 'workday' },
]

const SPONSORSHIP_OPTIONS: { label: string; value: SponsorshipStatus | '' }[] = [
  { label: 'Any sponsorship', value: '' },
  { label: 'Sponsors', value: 'sponsors' },
  { label: 'Unclear', value: 'unclear' },
  { label: 'No sponsorship', value: 'no_sponsorship' },
  { label: 'US citizen only', value: 'us_citizen_only' },
]

const MIN_SCORE_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'Any score', value: null },
  { label: '≥ 0.50', value: 0.5 },
  { label: '≥ 0.60', value: 0.6 },
  { label: '≥ 0.70', value: 0.7 },
  { label: '≥ 0.80', value: 0.8 },
]

interface Filters {
  keyword: string
  location: string
  company: string
  source: JobSource | ''
  sponsorship: SponsorshipStatus | ''
  hideDenials: boolean
  minScore: number | null
}

const EMPTY: Filters = {
  keyword: '',
  location: '',
  company: '',
  source: '',
  sponsorship: '',
  hideDenials: true,
  minScore: null,
}

export function JobsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [page, setPage] = useState(0)

  // Debounced free-text filters so we don't hammer the backend on every
  // keystroke. Selects + toggles apply immediately (single-event).
  const [debounced, setDebounced] = useState({
    keyword: '',
    location: '',
    company: '',
  })
  useEffect(() => {
    const id = setTimeout(
      () =>
        setDebounced({
          keyword: filters.keyword.trim(),
          location: filters.location.trim(),
          company: filters.company.trim(),
        }),
      DEBOUNCE_MS,
    )
    return () => clearTimeout(id)
  }, [filters.keyword, filters.location, filters.company])

  // Page must reset when any filter actually changes (debounced included).
  useEffect(() => {
    setPage(0)
  }, [
    debounced.keyword,
    debounced.location,
    debounced.company,
    filters.source,
    filters.sponsorship,
    filters.hideDenials,
    filters.minScore,
  ])

  const stats = useQuery({
    queryKey: ['jobs', 'stats'],
    queryFn: fetchJobStats,
  })

  const list = useQuery({
    queryKey: [
      'jobs',
      'list',
      debounced.keyword,
      debounced.location,
      debounced.company,
      filters.source,
      filters.sponsorship,
      filters.hideDenials,
      filters.minScore,
      page,
    ],
    queryFn: () =>
      fetchJobs({
        keyword: debounced.keyword || null,
        location: debounced.location || null,
        company: debounced.company || null,
        source: filters.source || null,
        sponsorship_status: filters.sponsorship || null,
        hide_denials: filters.hideDenials,
        min_score: filters.minScore,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    placeholderData: (prev) => prev,
  })

  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: async (v: {
      listingId: string
      next: ApplicationStatus | null
    }) => {
      if (v.next === null) return clearJobStatus(v.listingId)
      return upsertJobStatus(v.listingId, v.next)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs', 'list'] })
      qc.invalidateQueries({ queryKey: ['jobs', 'applications'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
    },
  })
  const onStatusChange = (
    listingId: string,
    next: ApplicationStatus | null,
  ) => mutation.mutate({ listingId, next })

  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1
  const hasActiveFilter = useMemo(
    () =>
      !!debounced.keyword ||
      !!debounced.location ||
      !!debounced.company ||
      !!filters.source ||
      !!filters.sponsorship ||
      filters.minScore != null ||
      !filters.hideDenials,
    [
      debounced.keyword,
      debounced.location,
      debounced.company,
      filters.source,
      filters.sponsorship,
      filters.minScore,
      filters.hideDenials,
    ],
  )

  return (
    <div className="min-h-screen p-6 lg:p-10">
      <div className="max-w-[1480px] mx-auto">
        <TopBar />

        <header className="mb-6 flex items-end justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight text-ink-900 leading-none">
              Jobs
            </h1>
            <p className="text-sm text-ink-500 mt-2">
              {list.data ? (
                <>
                  Showing {list.data.items.length} of{' '}
                  <span className="tabular text-ink-900 font-medium">
                    {list.data.total.toLocaleString()}
                  </span>{' '}
                  matching listings
                </>
              ) : (
                'Loading…'
              )}
            </p>
          </div>

          {stats.data && (
            <div className="flex items-center gap-6 text-right">
              <SummaryStat
                label="Total"
                value={stats.data.total.toLocaleString()}
                icon={<Briefcase className="h-4 w-4" />}
              />
              <SummaryStat
                label="Sponsors"
                value={(stats.data.by_sponsorship.sponsors ?? 0).toLocaleString()}
                icon={<Building2 className="h-4 w-4" />}
              />
              <SummaryStat
                label="Avg score"
                value={
                  stats.data.avg_match_score != null
                    ? stats.data.avg_match_score.toFixed(2)
                    : '—'
                }
                icon={<Gauge className="h-4 w-4" />}
              />
            </div>
          )}
        </header>

        {/* Filter bar */}
        <div className="bg-white rounded-3xl border border-cream-200 p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-3 items-center">
            <div className="lg:col-span-4 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-500" />
              <input
                value={filters.keyword}
                onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
                placeholder="Search title or description"
                className="w-full h-10 pl-9 pr-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              />
            </div>
            <div className="lg:col-span-3 relative">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-500" />
              <input
                value={filters.location}
                onChange={(e) => setFilters((f) => ({ ...f, location: e.target.value }))}
                placeholder="Location"
                className="w-full h-10 pl-9 pr-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              />
            </div>
            <div className="lg:col-span-3 relative">
              <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-500" />
              <input
                value={filters.company}
                onChange={(e) => setFilters((f) => ({ ...f, company: e.target.value }))}
                placeholder="Company"
                className="w-full h-10 pl-9 pr-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              />
            </div>
            <div className="lg:col-span-2">
              <button
                onClick={() => setFilters(EMPTY)}
                disabled={!hasActiveFilter}
                className="w-full h-10 px-3 rounded-full bg-cream-50 border border-cream-200 text-xs text-ink-700 hover:bg-amber-soft/40 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
              >
                <X className="h-3.5 w-3.5" />
                Reset
              </button>
            </div>

            {/* row 2 — selects + toggle */}
            <div className="lg:col-span-3">
              <select
                value={filters.source}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, source: e.target.value as JobSource | '' }))
                }
                className="w-full h-10 px-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              >
                {SOURCE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="lg:col-span-3">
              <select
                value={filters.sponsorship}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    sponsorship: e.target.value as SponsorshipStatus | '',
                  }))
                }
                className="w-full h-10 px-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              >
                {SPONSORSHIP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="lg:col-span-3">
              <select
                value={filters.minScore == null ? '' : String(filters.minScore)}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    minScore: e.target.value === '' ? null : Number(e.target.value),
                  }))
                }
                className="w-full h-10 px-3 rounded-full bg-cream-50 border border-cream-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-brand"
              >
                {MIN_SCORE_OPTIONS.map((o) => (
                  <option key={o.label} value={o.value ?? ''}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="lg:col-span-3 flex items-center gap-2 px-3 h-10 rounded-full bg-cream-50 border border-cream-200 text-sm text-ink-700 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={filters.hideDenials}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, hideDenials: e.target.checked }))
                }
                className="accent-amber-brand"
              />
              Hide explicit denials
            </label>
          </div>
        </div>

        {/* Listings */}
        <div className="bg-white rounded-3xl border border-cream-200 p-6">
          {list.isLoading ? (
            <div className="text-sm text-ink-500 py-12 text-center">Loading jobs…</div>
          ) : list.error ? (
            <div className="text-sm text-red-700 py-12 text-center">Failed to load jobs.</div>
          ) : !list.data || list.data.items.length === 0 ? (
            <div className="text-sm text-ink-500 py-12 text-center">
              No jobs match these filters.
            </div>
          ) : (
            <ul className="divide-y divide-cream-200">
              {list.data.items.map((job, i) => (
                <JobItem
                  key={job.id}
                  job={job}
                  rank={page * PAGE_SIZE + i + 1}
                  onStatusChange={(next) => onStatusChange(job.id, next)}
                  mutationPending={
                    mutation.isPending && mutation.variables?.listingId === job.id
                  }
                />
              ))}
            </ul>
          )}

          {list.data && list.data.total > PAGE_SIZE && (
            <div className="flex items-center justify-between mt-5 pt-4 border-t border-cream-200">
              <span className="text-xs text-ink-500">
                Page {page + 1} of {totalPages} · {list.data.total.toLocaleString()} jobs
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || list.isFetching}
                  className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-amber-soft/40"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page + 1 >= totalPages || list.isFetching}
                  className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-amber-soft/40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---- helpers ----

function SummaryStat({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-9 w-9 rounded-full bg-cream-200/70 flex items-center justify-center text-ink-700">
        {icon}
      </span>
      <div>
        <div className="text-2xl font-semibold tabular leading-none text-ink-900">{value}</div>
        <div className="text-xs text-ink-500 mt-0.5">{label}</div>
      </div>
    </div>
  )
}

const STATUS_PILL: Record<ApplicationStatus, string> = {
  saved: 'bg-cream-200 text-ink-700 border border-cream-200',
  applied: 'bg-amber-brand text-ink-900',
  interviewing: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
  offer: 'bg-emerald-200 text-emerald-900',
  rejected: 'bg-red-50 text-red-700 border border-red-200',
  withdrawn: 'bg-cream-100 text-ink-500 border border-cream-200',
}

const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

const STATUS_OPTIONS: (ApplicationStatus | 'clear')[] = [
  'saved',
  'applied',
  'interviewing',
  'offer',
  'rejected',
  'withdrawn',
  'clear',
]

function JobItem({
  job,
  rank,
  onStatusChange,
  mutationPending,
}: {
  job: JobRow
  rank: number
  onStatusChange: (next: ApplicationStatus | null) => void
  mutationPending: boolean
}) {
  const sponsorOK =
    job.sponsorship_status === 'sponsors' ||
    (job.sponsorship_status === 'unclear' && (job.h1b_lca_count_recent ?? 0) > 0)
  const denial =
    job.sponsorship_status === 'no_sponsorship' ||
    job.sponsorship_status === 'us_citizen_only'
  const currentStatus = job.user_status?.status ?? null

  return (
    <li className="py-3 flex items-start gap-3">
      <div className="h-9 w-9 rounded-xl bg-cream-100 flex items-center justify-center text-xs font-medium text-ink-700 shrink-0 tabular">
        {rank}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-ink-900 truncate">{job.company}</span>
          {currentStatus && (
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide flex items-center gap-1 ${STATUS_PILL[currentStatus]}`}
            >
              {currentStatus === 'saved' ? (
                <Bookmark className="h-2.5 w-2.5" />
              ) : (
                <CheckCircle2 className="h-2.5 w-2.5" />
              )}
              {STATUS_LABEL[currentStatus]}
            </span>
          )}
          {sponsorOK && (
            <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-amber-brand text-ink-900">
              sponsors
            </span>
          )}
          {denial && (
            <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-red-50 text-red-700 border border-red-200">
              {job.sponsorship_status === 'us_citizen_only' ? 'citizens only' : 'no sponsorship'}
            </span>
          )}
          {job.cpt_opt_friendly && (
            <span className="text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide bg-ink-900 text-amber-soft flex items-center gap-1">
              <Sparkles className="h-2.5 w-2.5" />
              CPT/OPT
            </span>
          )}
          {job.h1b_lca_count_recent != null && job.h1b_lca_count_recent > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cream-100 text-ink-700">
              {job.h1b_lca_count_recent} LCAs/yr
            </span>
          )}
        </div>

        <div className="text-sm text-ink-700 truncate mt-0.5">{job.title}</div>

        <div className="mt-1 flex items-center gap-3 text-xs text-ink-500 flex-wrap">
          {job.location && (
            <span className="flex items-center gap-1 min-w-0">
              <MapPin className="h-3 w-3 shrink-0" />
              <span className="truncate">{job.location}</span>
            </span>
          )}
          <span>{SOURCE_LABEL[job.source] ?? job.source}</span>
          {job.sponsorship_evidence && (
            <span
              className="truncate max-w-md text-ink-500/80"
              title={job.sponsorship_evidence}
            >
              · {job.sponsorship_evidence}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col items-end gap-1.5 shrink-0">
        <span className="text-sm font-medium tabular text-ink-900">
          {job.match_score != null ? job.match_score.toFixed(2) : '—'}
        </span>
        <div className="flex items-center gap-1.5">
          <select
            value={currentStatus ?? ''}
            disabled={mutationPending}
            onChange={(e) => {
              const v = e.target.value as ApplicationStatus | '' | 'clear'
              if (v === '' || v === 'clear') onStatusChange(null)
              else onStatusChange(v)
            }}
            className={`text-xs px-2 py-1 rounded-full border border-cream-200 bg-cream-50 text-ink-700 focus:outline-none focus:ring-2 focus:ring-amber-brand disabled:opacity-50 ${
              currentStatus ? STATUS_PILL[currentStatus] : ''
            }`}
            aria-label="Application status"
          >
            <option value="">Track…</option>
            {STATUS_OPTIONS.map((s) =>
              s === 'clear' ? (
                <option key={s} value="clear">
                  ✕ Untrack
                </option>
              ) : (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ),
            )}
          </select>
          {job.source_url && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noreferrer"
              className="h-7 w-7 rounded-full bg-cream-100 flex items-center justify-center hover:bg-amber-brand transition-colors"
              aria-label="Open posting"
            >
              <ExternalLink className="h-3 w-3 text-ink-700" />
            </a>
          )}
        </div>
      </div>
    </li>
  )
}
