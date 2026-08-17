import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Loader2, Send, Sparkles, X } from 'lucide-react'
import { MUTATING_INTENTS, runAgent, type AgentResponse } from '../lib/api'
import {
  CustomizeResumeView,
  SearchJobsView,
  TriageEmailsView,
  isCustomizeResumeResult,
  isSearchJobsResult,
  isTriageEmailsResult,
} from './AgentResultViews'

/** Which intents get a rich structured view instead of the raw JSON dump. */
function renderRichResult(intent: string, toolResult: unknown) {
  if (intent === 'search_jobs' && isSearchJobsResult(toolResult)) {
    return <SearchJobsView data={toolResult} />
  }
  if (intent === 'triage_emails' && isTriageEmailsResult(toolResult)) {
    return <TriageEmailsView data={toolResult} />
  }
  if (intent === 'customize_resume' && isCustomizeResumeResult(toolResult)) {
    return <CustomizeResumeView data={toolResult} />
  }
  return null
}

const SUGGESTIONS = [
  'Show SDE intern jobs posted in the last 2 days',
  'What emails are urgent right now?',
  'Find ML engineer roles that sponsor H-1B',
  'Pull more Greenhouse backend engineer jobs',
]

export function AgentBar() {
  const [q, setQ] = useState('')
  const [lastResult, setLastResult] = useState<AgentResponse | null>(null)
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (message: string) => runAgent(message),
    onSuccess: (data) => {
      setLastResult(data)
      if (MUTATING_INTENTS.has(data.intent)) {
        qc.invalidateQueries({ queryKey: ['overview'] })
      }
    },
  })

  const submit = (msg: string) => {
    const trimmed = msg.trim()
    if (!trimmed || mutation.isPending) return
    mutation.mutate(trimmed)
    setQ('')
  }

  return (
    <div className="mb-8">
      {/* Search pill */}
      <div className="relative">
        <div className="absolute inset-y-0 left-5 flex items-center pointer-events-none">
          <Sparkles className="h-5 w-5 text-amber-strong" />
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit(q)
          }}
          placeholder="Ask Nexus — 'show ML jobs at Anthropic', 'pull SDE intern listings', 'what emails are urgent?'"
          disabled={mutation.isPending}
          className="w-full h-16 pl-14 pr-32 rounded-full bg-white border border-cream-200 text-ink-900 placeholder:text-ink-500/70 focus:outline-none focus:ring-2 focus:ring-amber-brand focus:border-transparent text-base disabled:opacity-50"
        />
        <button
          onClick={() => submit(q)}
          disabled={mutation.isPending || !q.trim()}
          className="absolute inset-y-2 right-2 px-5 rounded-full bg-ink-900 text-white flex items-center gap-2 hover:bg-ink-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {mutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          <span className="text-sm font-medium">Ask</span>
        </button>
      </div>

      {/* Suggestion chips — hide once user has interacted */}
      {!lastResult && !mutation.isPending && (
        <div className="flex flex-wrap gap-2 mt-3 px-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="text-xs px-3 py-1.5 rounded-full bg-cream-50 border border-cream-200 text-ink-700 hover:bg-amber-soft/40 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Loading state */}
      {mutation.isPending && (
        <div className="mt-4 bg-white rounded-3xl border border-cream-200 p-6 flex items-center gap-3 text-ink-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Routing through the master agent…</span>
        </div>
      )}

      {/* Error state */}
      {mutation.isError && (
        <div className="mt-4 bg-white rounded-3xl border border-red-200 p-6 text-red-700 text-sm">
          Agent call failed. Make sure the FastAPI backend is running on
          <code className="mx-1 bg-red-50 px-1.5 rounded">127.0.0.1:8000</code>.
        </div>
      )}

      {/* Result panel */}
      {lastResult && !mutation.isPending && (
        <div className="mt-4 bg-white rounded-3xl border border-cream-200 p-6">
          <div className="flex items-center justify-between mb-3 gap-3">
            <div className="flex items-center gap-2 flex-wrap min-w-0">
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-soft text-ink-900 shrink-0">
                {lastResult.intent || 'unknown'}
              </span>
              {lastResult.classifier_reasoning && (
                <span className="text-xs text-ink-500 truncate">
                  {lastResult.classifier_reasoning}
                </span>
              )}
            </div>
            <button
              onClick={() => setLastResult(null)}
              className="h-7 w-7 rounded-full flex items-center justify-center text-ink-500 hover:bg-cream-100 hover:text-ink-900 transition-colors shrink-0"
              aria-label="Clear"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {lastResult.error ? (
            <p className="text-sm text-red-700">{lastResult.error}</p>
          ) : (
            (() => {
              const rich = renderRichResult(
                lastResult.intent,
                lastResult.tool_result,
              )
              if (rich) {
                // Structured card takes over — the model's prose is redundant
                // when we can show the actual rows. Still show classifier
                // response as a short lead-in if it's short.
                return (
                  <>
                    {lastResult.response && (
                      <div className="text-sm text-ink-700 leading-relaxed">
                        {lastResult.response}
                      </div>
                    )}
                    {rich}
                  </>
                )
              }
              return (
                <>
                  <div className="text-sm text-ink-900 whitespace-pre-wrap leading-relaxed">
                    {lastResult.response}
                  </div>
                  {!!lastResult.tool_result && (
                    <details className="mt-4 group">
                      <summary className="text-xs text-ink-500 cursor-pointer flex items-center gap-1 hover:text-ink-900 list-none">
                        <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
                        Raw tool result
                      </summary>
                      <pre className="mt-2 text-[11px] bg-cream-50 rounded-xl p-3 overflow-x-auto max-h-64 text-ink-700">
                        {JSON.stringify(lastResult.tool_result, null, 2)}
                      </pre>
                    </details>
                  )}
                </>
              )
            })()
          )}
        </div>
      )}
    </div>
  )
}
