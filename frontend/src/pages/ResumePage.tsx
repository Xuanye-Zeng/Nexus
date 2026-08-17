import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check, Copy, Download, Loader2, Sparkles, Wand2 } from 'lucide-react'
import { TopBar } from '../components/TopBar'
import { Card, CardHeader } from '../components/Card'
import {
  customizeResume,
  downloadResumePdf,
  type CustomizeResponse,
  type SponsorshipStatus,
} from '../lib/api'
import {
  parseRewrite,
  rewriteToPlainText,
  type RewrittenSection,
} from '../lib/parseRewrite'

export function ResumePage() {
  const [jd, setJd] = useState('')

  const mutation = useMutation({
    mutationFn: (jdText: string) => customizeResume(jdText),
  })

  const sections = useMemo<RewrittenSection[]>(
    () => (mutation.data ? parseRewrite(mutation.data.rewritten_resume) : []),
    [mutation.data],
  )

  const canSubmit = jd.trim().length >= 50 && !mutation.isPending

  return (
    <div className="min-h-screen p-6 lg:p-10">
      <div className="max-w-[1480px] mx-auto">
        <TopBar />

        <div className="mb-8">
          <h1 className="text-4xl font-semibold tracking-tight text-ink-900 leading-none mb-3">
            Customize resume for a JD
          </h1>
          <p className="text-ink-500 text-sm max-w-2xl">
            Paste a job description. Nexus runs the JD against your master
            resume — RAG-narrows the most relevant project/experience
            sections, rewrites bullets to mirror JD language while preserving
            every number from your originals, and surfaces the sponsorship
            verdict for the role.
          </p>
        </div>

        <div className="grid grid-cols-12 gap-6 items-start">
          {/* Left — paste JD + submit */}
          <div className="col-span-12 lg:col-span-5">
            <Card>
              <CardHeader
                title="Paste the JD"
                right={
                  <span className="text-xs text-ink-500 tabular">
                    {jd.length.toLocaleString()} chars
                  </span>
                }
              />
              <textarea
                value={jd}
                onChange={(e) => setJd(e.target.value)}
                disabled={mutation.isPending}
                placeholder="Paste the full job description here — title, responsibilities, qualifications, sponsorship language. Min 50 characters."
                className="w-full h-[420px] rounded-2xl border border-cream-200 bg-cream-50/40 p-4 text-sm text-ink-900 placeholder:text-ink-500/70 focus:outline-none focus:ring-2 focus:ring-amber-brand focus:border-transparent resize-none disabled:opacity-50"
              />
              <button
                onClick={() => canSubmit && mutation.mutate(jd)}
                disabled={!canSubmit}
                className="mt-4 w-full h-12 rounded-full bg-ink-900 text-white flex items-center justify-center gap-2 hover:bg-ink-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {mutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Customizing — Groq llama-3.3-70b…</span>
                  </>
                ) : (
                  <>
                    <Wand2 className="h-4 w-4" />
                    <span className="font-medium">Customize my resume</span>
                  </>
                )}
              </button>
              <div className="mt-3 text-[11px] text-ink-500 leading-relaxed">
                Typical round-trip: 8–14s. Each call hits Groq's daily token
                budget (100K TPD on llama-3.3-70b); ~15 customizes/day at
                free tier.
              </div>
            </Card>
          </div>

          {/* Right — result */}
          <div className="col-span-12 lg:col-span-7 space-y-6">
            {mutation.isError && (
              <Card>
                <div className="text-sm text-red-700">
                  Customize call failed. If the message mentions "rate limit",
                  Groq's daily token cap was hit — wait until midnight UTC or
                  upgrade to Groq Dev tier.
                </div>
              </Card>
            )}

            {mutation.isPending && (
              <Card>
                <div className="flex items-center gap-3 text-ink-500">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span>
                    Running jd_keyword_extractor → RAG → bullet_rewriter →
                    sponsorship_classifier…
                  </span>
                </div>
              </Card>
            )}

            {mutation.data && <ResultPanels data={mutation.data} sections={sections} />}

            {!mutation.data && !mutation.isPending && !mutation.isError && (
              <Card>
                <div className="text-sm text-ink-500">
                  Result appears here once the customize call returns:
                  sponsorship verdict at the top, then the rewritten bullets
                  with BEFORE / AFTER / REASON for each, plus a one-click
                  copy of the final resume.
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- Result subcomponents ----

const SPONSORSHIP_LABEL: Record<SponsorshipStatus, string> = {
  sponsors: 'Sponsors visas',
  no_sponsorship: 'No sponsorship',
  us_citizen_only: 'US citizen only',
  unclear: 'Unclear',
}

const SPONSORSHIP_CLS: Record<SponsorshipStatus, string> = {
  sponsors: 'bg-amber-brand text-ink-900',
  no_sponsorship: 'bg-ink-900 text-white',
  us_citizen_only: 'bg-ink-700 text-white',
  unclear: 'bg-cream-200 text-ink-700',
}

function ResultPanels({
  data,
  sections,
}: {
  data: CustomizeResponse
  sections: RewrittenSection[]
}) {
  const plain = useMemo(() => rewriteToPlainText(sections), [sections])

  return (
    <>
      <SponsorshipCard verdict={data.sponsorship} />
      <RewriteCard
        sections={sections}
        plain={plain}
        rawMarkdown={data.rewritten_resume}
      />
      <ExtractionCard text={data.jd_extraction} />
      <AuditCard data={data} />
    </>
  )
}

function SponsorshipCard({ verdict }: { verdict: CustomizeResponse['sponsorship'] }) {
  const status = verdict.status as SponsorshipStatus
  return (
    <Card>
      <CardHeader
        title="Sponsorship verdict"
        right={
          <span className="text-xs text-ink-500 tabular">
            confidence {(verdict.confidence * 100).toFixed(0)}%
          </span>
        }
      />
      <div className="flex items-center gap-3 flex-wrap">
        <span
          className={`text-xs px-3 py-1 rounded-full font-medium uppercase tracking-wide ${SPONSORSHIP_CLS[status]}`}
        >
          {SPONSORSHIP_LABEL[status]}
        </span>
        {verdict.cpt_opt_friendly && (
          <span className="text-xs px-3 py-1 rounded-full bg-ink-900 text-amber-soft flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            CPT/OPT
          </span>
        )}
      </div>
      {verdict.evidence && (
        <blockquote className="mt-4 text-sm text-ink-700 border-l-2 border-amber-brand pl-3 italic">
          "{verdict.evidence}"
        </blockquote>
      )}
      <div className="mt-3 text-xs text-ink-500">{verdict.reasoning}</div>
    </Card>
  )
}

function RewriteCard({
  sections,
  plain,
  rawMarkdown,
}: {
  sections: RewrittenSection[]
  plain: string
  rawMarkdown: string
}) {
  const [copied, setCopied] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const copyAll = async () => {
    await navigator.clipboard.writeText(plain)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const hasContent = rawMarkdown.trim().length > 0

  const downloadPdf = async () => {
    if (!hasContent || downloading) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const blob = await downloadResumePdf(rawMarkdown, 'Alex Zeng')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'Alex_Zeng_resume.pdf'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : 'PDF download failed')
    } finally {
      setDownloading(false)
    }
  }

  // Count bullets to show in header
  const totals = sections.reduce(
    (acc, s) => {
      for (const item of s.items) {
        for (const b of item.bullets) {
          acc.total += 1
          if (b.kept) acc.kept += 1
          else acc.rewritten += 1
        }
      }
      return acc
    },
    { total: 0, kept: 0, rewritten: 0 },
  )

  return (
    <Card>
      <CardHeader
        title="Rewritten resume"
        right={
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-500 tabular">
              {totals.rewritten} rewritten · {totals.kept} kept
            </span>
            <button
              onClick={downloadPdf}
              disabled={!hasContent || downloading}
              className="text-xs px-3 py-1.5 rounded-full bg-cream-100 text-ink-900 hover:bg-cream-200 transition-colors flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {downloading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Download className="h-3 w-3" />
              )}
              {downloading ? 'Rendering…' : 'Download PDF'}
            </button>
            <button
              onClick={copyAll}
              className="text-xs px-3 py-1.5 rounded-full bg-ink-900 text-white hover:bg-ink-700 transition-colors flex items-center gap-1.5"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? 'Copied' : 'Copy final'}
            </button>
          </div>
        }
      />
      {downloadError && (
        <div className="mb-3 text-xs text-red-700">{downloadError}</div>
      )}

      <div className="space-y-6">
        {sections.map((section) => (
          <div key={section.name}>
            <h3 className="text-xs uppercase tracking-wider text-ink-500 mb-2">
              {section.name}
            </h3>
            {section.preamble.map((p, i) => (
              <p key={i} className="text-sm text-ink-700 mb-1">
                {p}
              </p>
            ))}
            <div className="space-y-4">
              {section.items.map((item, ii) => (
                <div key={ii}>
                  <div className="text-sm font-medium text-ink-900 mb-2">
                    {item.heading}
                  </div>
                  <ul className="space-y-2">
                    {item.bullets.map((b, bi) => (
                      <BulletRow key={bi} bullet={b} />
                    ))}
                    {item.raw_lines.map((r, ri) => (
                      <li key={`r${ri}`} className="text-sm text-ink-700">
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function BulletRow({
  bullet,
}: {
  bullet: {
    before: string
    after: string
    final: string
    reason: string
    kept: boolean
  }
}) {
  const [showDiff, setShowDiff] = useState(false)

  return (
    <li>
      <div className="flex items-start gap-2">
        <span className="text-amber-strong shrink-0 mt-1.5">•</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-ink-900 leading-relaxed">{bullet.final}</p>
          <div className="flex items-center gap-2 mt-1 text-[11px]">
            {bullet.kept && (
              <span className="px-1.5 py-0.5 rounded bg-cream-100 text-ink-500 uppercase tracking-wider">
                kept
              </span>
            )}
            <button
              onClick={() => setShowDiff((v) => !v)}
              className="text-ink-500 hover:text-ink-900"
            >
              {showDiff ? 'hide' : 'why'}
            </button>
          </div>
          {showDiff && (
            <div className="mt-2 space-y-1.5 text-xs">
              {!bullet.kept && (
                <div className="text-ink-500">
                  <span className="uppercase tracking-wider text-[10px] mr-1">
                    before:
                  </span>
                  {bullet.before}
                </div>
              )}
              {bullet.reason && (
                <div className="text-ink-700 italic">
                  <span className="uppercase tracking-wider text-[10px] mr-1 not-italic">
                    reason:
                  </span>
                  {bullet.reason}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

function ExtractionCard({ text }: { text: string }) {
  return (
    <Card>
      <details>
        <summary className="cursor-pointer flex items-center justify-between list-none">
          <h3 className="text-base font-medium text-ink-900">JD signal extraction</h3>
          <span className="text-xs text-ink-500">expand</span>
        </summary>
        <pre className="mt-4 text-xs text-ink-700 bg-cream-50 rounded-xl p-3 overflow-x-auto whitespace-pre-wrap leading-relaxed">
          {text}
        </pre>
      </details>
    </Card>
  )
}

function AuditCard({ data }: { data: CustomizeResponse }) {
  return (
    <Card>
      <details>
        <summary className="cursor-pointer flex items-center justify-between list-none">
          <h3 className="text-base font-medium text-ink-900">Pipeline audit</h3>
          <span className="text-xs text-ink-500">
            sections used · prompt versions
          </span>
        </summary>
        <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
          <div>
            <div className="text-ink-500 uppercase tracking-wider mb-2">
              Sections sent
            </div>
            <ul className="space-y-1">
              {data.sections_used.map((s, i) => (
                <li key={i} className="text-ink-700">
                  <span className="font-mono text-[10px] mr-1">
                    [{s.source}]
                  </span>
                  {s.section_type} — {s.label}
                  {s.distance != null && (
                    <span className="text-ink-500 ml-2 tabular">
                      dist {s.distance.toFixed(3)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-ink-500 uppercase tracking-wider mb-2">
              Prompt versions
            </div>
            <ul className="space-y-1">
              {Object.entries(data.prompt_versions).map(([k, v]) => (
                <li key={k} className="text-ink-700 font-mono">
                  {k}: v{v}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </details>
    </Card>
  )
}
