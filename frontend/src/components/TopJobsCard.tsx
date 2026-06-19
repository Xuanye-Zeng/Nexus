import { Clock, ExternalLink, MapPin, Sparkles } from 'lucide-react'
import type { TopJob } from '../lib/api'
import { relativeTime } from '../lib/relativeTime'
import { Card, CardHeader } from './Card'

interface Props {
  jobs: TopJob[]
}

const SOURCE_LABEL: Record<string, string> = {
  adzuna: 'Adzuna',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
}

export function TopJobsCard({ jobs }: Props) {
  return (
    <Card>
      <CardHeader
        title="Daily job feed"
        right={
          <span className="text-xs text-ink-500">
            newest first · sponsor-friendly only
          </span>
        }
      />

      <ul className="divide-y divide-cream-200">
        {jobs.map((j, i) => {
          const sponsorOK =
            j.sponsorship_status === 'sponsors' ||
            (j.sponsorship_status === 'unclear' && (j.h1b_lca_count_recent ?? 0) > 0)
          return (
            <li key={j.id} className="py-3 flex items-start gap-3">
              <div className="h-9 w-9 rounded-xl bg-cream-100 flex items-center justify-center text-xs font-medium text-ink-700 shrink-0">
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
                  {j.h1b_lca_count_recent != null && j.h1b_lca_count_recent > 0 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cream-100 text-ink-700">
                      {j.h1b_lca_count_recent} LCAs/yr
                    </span>
                  )}
                </div>

                {/* row 2: title */}
                <div className="text-sm text-ink-700 truncate mt-0.5">{j.title}</div>

                {/* row 3: meta line — location · source · posted-ago */}
                <div className="mt-1 flex items-center gap-3 text-xs text-ink-500 flex-wrap">
                  {j.location && (
                    <span className="flex items-center gap-1 min-w-0">
                      <MapPin className="h-3 w-3 shrink-0" />
                      <span className="truncate">{j.location}</span>
                    </span>
                  )}
                  <span>{SOURCE_LABEL[j.source] ?? j.source}</span>
                  {j.scraped_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {relativeTime(j.scraped_at)}
                    </span>
                  )}
                </div>
              </div>

              {/* right column: match score + url */}
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <span className="text-sm font-medium tabular">
                  {j.match_score != null ? j.match_score.toFixed(2) : '—'}
                </span>
                {j.source_url && (
                  <a
                    href={j.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="h-7 w-7 rounded-full bg-cream-100 flex items-center justify-center hover:bg-amber-brand transition-colors"
                  >
                    <ExternalLink className="h-3 w-3 text-ink-700" />
                  </a>
                )}
              </div>
            </li>
          )
        })}
        {jobs.length === 0 && (
          <li className="py-8 text-center text-sm text-ink-500">
            No matches yet — run <code className="bg-cream-100 px-1 rounded">ingest_jobs</code> from the agent.
          </li>
        )}
      </ul>
    </Card>
  )
}
