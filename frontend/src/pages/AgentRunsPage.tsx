import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Gauge,
  HelpCircle,
  Timer,
  XCircle,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  fetchAgentRuns,
  fetchAgentRunsStats,
  type AgentRun,
  type AgentRunStatus,
} from '../lib/api'
import { TopBar } from '../components/TopBar'
import { relativeTime } from '../lib/relativeTime'

const PAGE_SIZE = 20

const STATUS_STYLES: Record<AgentRunStatus, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  success: { label: 'Success', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  clarify: { label: 'Clarify', cls: 'bg-amber-soft text-ink-900 border-amber-200', icon: HelpCircle },
  error: { label: 'Error', cls: 'bg-red-50 text-red-700 border-red-200', icon: XCircle },
  tool_error: { label: 'Tool error', cls: 'bg-orange-50 text-orange-700 border-orange-200', icon: AlertTriangle },
}

const STATUS_OPTIONS: { label: string; value: AgentRunStatus | '' }[] = [
  { label: 'All statuses', value: '' },
  { label: 'Success', value: 'success' },
  { label: 'Clarify', value: 'clarify' },
  { label: 'Error', value: 'error' },
  { label: 'Tool error', value: 'tool_error' },
]

export function AgentRunsPage() {
  const [intentFilter, setIntentFilter] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<AgentRunStatus | ''>('')
  const [page, setPage] = useState(0)

  const stats = useQuery({
    queryKey: ['agent-runs', 'stats'],
    queryFn: fetchAgentRunsStats,
  })

  const runs = useQuery({
    queryKey: ['agent-runs', 'list', intentFilter, statusFilter, page],
    queryFn: () =>
      fetchAgentRuns({
        intent: intentFilter || null,
        status: statusFilter || null,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    placeholderData: (prev) => prev,
  })

  const intentOptions = useMemo(() => {
    const fromStats = stats.data ? Object.keys(stats.data.by_intent).sort() : []
    return ['', ...fromStats]
  }, [stats.data])

  const intentBarData = useMemo(() => {
    if (!stats.data) return []
    return Object.entries(stats.data.by_intent)
      .map(([intent, count]) => ({ intent: intent || 'unknown', count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10)
  }, [stats.data])

  const totalPages = runs.data ? Math.max(1, Math.ceil(runs.data.total / PAGE_SIZE)) : 1

  const setIntent = (next: string) => {
    setIntentFilter(next)
    setPage(0)
  }
  const setStatus = (next: AgentRunStatus | '') => {
    setStatusFilter(next)
    setPage(0)
  }

  return (
    <div className="min-h-screen p-6 lg:p-10">
      <div className="max-w-[1480px] mx-auto">
        <TopBar />

        <header className="mb-8">
          <h1 className="text-4xl font-semibold tracking-tight text-ink-900 leading-none">
            Agent runs
          </h1>
          <p className="text-sm text-ink-500 mt-2">
            Every Master Agent turn — intent, latency, response. Newest first.
          </p>
        </header>

        {/* Stats row — total / avg / p95 / by_status */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <StatTile
            label="Total runs"
            value={stats.data ? stats.data.total.toLocaleString() : '—'}
            icon={<Activity className="h-4 w-4" />}
          />
          <StatTile
            label="Avg latency"
            value={formatMs(stats.data?.avg_latency_ms)}
            icon={<Timer className="h-4 w-4" />}
          />
          <StatTile
            label="p95 latency"
            value={formatMs(stats.data?.p95_latency_ms)}
            icon={<Gauge className="h-4 w-4" />}
          />
          <StatusBreakdown by_status={stats.data?.by_status} />
        </div>

        <div className="grid grid-cols-12 gap-6 items-start">
          {/* Left — intent histogram */}
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-3xl border border-cream-200 p-6">
              <h2 className="text-sm font-semibold text-ink-900 mb-1">Top intents</h2>
              <p className="text-xs text-ink-500 mb-4">
                Counts across all runs (max 10 shown)
              </p>
              <div className="h-72">
                {intentBarData.length === 0 ? (
                  <EmptyChart />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={intentBarData}
                      layout="vertical"
                      margin={{ top: 4, right: 16, bottom: 4, left: 24 }}
                    >
                      <CartesianGrid horizontal={false} stroke="#f1ecdf" />
                      <XAxis type="number" stroke="#a59c87" fontSize={11} allowDecimals={false} />
                      <YAxis
                        type="category"
                        dataKey="intent"
                        stroke="#7b7460"
                        fontSize={11}
                        width={120}
                      />
                      <Tooltip
                        cursor={{ fill: '#fdf6e3' }}
                        contentStyle={{
                          borderRadius: 12,
                          border: '1px solid #e8e0c8',
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="count" fill="#d4a017" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>

          {/* Right — runs timeline */}
          <div className="col-span-12 lg:col-span-7">
            <div className="bg-white rounded-3xl border border-cream-200 p-6">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
                <h2 className="text-sm font-semibold text-ink-900">Timeline</h2>
                <div className="flex flex-wrap gap-2">
                  <select
                    value={intentFilter}
                    onChange={(e) => setIntent(e.target.value)}
                    className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 focus:outline-none focus:ring-2 focus:ring-amber-brand"
                  >
                    {intentOptions.map((o) => (
                      <option key={o} value={o}>
                        {o ? o : 'All intents'}
                      </option>
                    ))}
                  </select>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatus(e.target.value as AgentRunStatus | '')}
                    className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 focus:outline-none focus:ring-2 focus:ring-amber-brand"
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {runs.isLoading ? (
                <div className="text-sm text-ink-500 py-12 text-center">Loading runs…</div>
              ) : runs.error ? (
                <div className="text-sm text-red-700 py-12 text-center">
                  Failed to load runs.
                </div>
              ) : !runs.data || runs.data.items.length === 0 ? (
                <div className="text-sm text-ink-500 py-12 text-center">
                  No runs match these filters yet.
                </div>
              ) : (
                <ol className="space-y-3">
                  {runs.data.items.map((run) => (
                    <RunRow key={run.id} run={run} />
                  ))}
                </ol>
              )}

              {runs.data && runs.data.total > PAGE_SIZE && (
                <div className="flex items-center justify-between mt-5 pt-4 border-t border-cream-200">
                  <span className="text-xs text-ink-500">
                    Page {page + 1} of {totalPages} · {runs.data.total.toLocaleString()} runs
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0 || runs.isFetching}
                      className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-amber-soft/40"
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => setPage((p) => p + 1)}
                      disabled={page + 1 >= totalPages || runs.isFetching}
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
      </div>
    </div>
  )
}

// ---- Helpers ----

function formatMs(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function StatTile({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-3xl border border-cream-200 p-5">
      <div className="flex items-center gap-2 text-ink-500 text-xs uppercase tracking-wider">
        <span className="h-7 w-7 rounded-full bg-cream-100 flex items-center justify-center text-ink-700">
          {icon}
        </span>
        {label}
      </div>
      <div className="text-3xl font-semibold text-ink-900 mt-2 tabular leading-none">
        {value}
      </div>
    </div>
  )
}

function StatusBreakdown({ by_status }: { by_status: Record<string, number> | undefined }) {
  const entries = by_status ? Object.entries(by_status) : []
  return (
    <div className="bg-white rounded-3xl border border-cream-200 p-5">
      <div className="text-ink-500 text-xs uppercase tracking-wider mb-2">By status</div>
      {entries.length === 0 ? (
        <div className="text-sm text-ink-500">—</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([s, c]) => {
            const meta = STATUS_STYLES[s as AgentRunStatus]
            const cls = meta?.cls ?? 'bg-cream-50 text-ink-700 border-cream-200'
            const label = meta?.label ?? s
            return (
              <span
                key={s}
                className={`text-xs px-2.5 py-0.5 rounded-full border ${cls}`}
              >
                {label} <span className="tabular font-medium">{c}</span>
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

function EmptyChart() {
  return (
    <div className="h-full flex items-center justify-center text-xs text-ink-500">
      No data yet — ask the agent something to populate this.
    </div>
  )
}

function RunRow({ run }: { run: AgentRun }) {
  const [open, setOpen] = useState(false)
  const meta = STATUS_STYLES[run.status] ?? STATUS_STYLES.success
  const StatusIcon = meta.icon
  const hasDetail = !!(run.response || run.classifier_reasoning || run.error)

  return (
    <li className="border border-cream-200 rounded-2xl overflow-hidden">
      <button
        onClick={() => hasDetail && setOpen((v) => !v)}
        className={`w-full text-left p-4 flex items-start gap-3 ${
          hasDetail ? 'hover:bg-cream-50/60 cursor-pointer' : 'cursor-default'
        }`}
      >
        <span className={`h-7 w-7 rounded-full flex items-center justify-center border ${meta.cls}`}>
          <StatusIcon className="h-3.5 w-3.5" />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-soft text-ink-900">
              {run.intent || 'unknown'}
            </span>
            <span className="text-xs text-ink-500">{relativeTime(run.created_at)}</span>
            {run.latency_ms != null && (
              <span className="text-xs text-ink-500">· {formatMs(run.latency_ms)}</span>
            )}
            {run.module && run.module !== 'master_agent' && (
              <span className="text-[10px] uppercase tracking-wider text-ink-500">
                · {run.module}
              </span>
            )}
          </div>
          {run.input_summary && (
            <p className="mt-1 text-sm text-ink-900 truncate">{run.input_summary}</p>
          )}
        </div>

        {hasDetail && (
          <ChevronDown
            className={`h-4 w-4 text-ink-500 shrink-0 mt-1 transition-transform ${
              open ? 'rotate-180' : ''
            }`}
          />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-cream-200 bg-cream-50/40 space-y-3">
          {run.classifier_reasoning && (
            <DetailBlock label="Classifier reasoning" body={run.classifier_reasoning} />
          )}
          {run.response && <DetailBlock label="Response" body={run.response} />}
          {run.error && (
            <DetailBlock label="Error" body={run.error} tone="error" />
          )}
          {run.langsmith_trace_id && (
            <div className="text-[11px] text-ink-500">
              LangSmith trace:{' '}
              <code className="bg-cream-100 px-1.5 py-0.5 rounded">
                {run.langsmith_trace_id}
              </code>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function DetailBlock({
  label,
  body,
  tone,
}: {
  label: string
  body: string
  tone?: 'error'
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-1">{label}</div>
      <div
        className={`text-xs whitespace-pre-wrap leading-relaxed ${
          tone === 'error' ? 'text-red-700' : 'text-ink-900'
        }`}
      >
        {body}
      </div>
    </div>
  )
}
