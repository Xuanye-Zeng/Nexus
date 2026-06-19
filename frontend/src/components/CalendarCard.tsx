import { Calendar as CalendarIcon, DollarSign } from 'lucide-react'
import type { UrgentEmail } from '../lib/api'
import { Card, CardHeader } from './Card'

const EVENT_CATEGORIES = new Set(['interview', 'offer'])

interface Props {
  emails: UrgentEmail[]
}

/** Until M4 (Microsoft Graph / Google Calendar OAuth) ships, derive a
 *  "what's upcoming" view from interview + offer emails already classified
 *  by the M3 pipeline. Honest about the source via the footer note. */
export function CalendarCard({ emails }: Props) {
  const upcoming = emails
    .filter((e) => e.category && EVENT_CATEGORIES.has(e.category))
    .sort((a, b) => {
      // Higher importance first, then most recently received
      const impA = a.importance_score ?? 0
      const impB = b.importance_score ?? 0
      if (impA !== impB) return impB - impA
      const tA = a.received_at ? new Date(a.received_at).getTime() : 0
      const tB = b.received_at ? new Date(b.received_at).getTime() : 0
      return tB - tA
    })

  return (
    <Card>
      <CardHeader
        title="Upcoming"
        right={<span className="text-xs text-ink-500">from inbox</span>}
      />

      <ul className="space-y-3">
        {upcoming.map((e) => {
          const Icon = e.category === 'offer' ? DollarSign : CalendarIcon
          const tone =
            e.category === 'offer'
              ? 'bg-amber-brand text-ink-900'
              : 'bg-ink-900 text-amber-soft'
          return (
            <li key={e.id} className="flex gap-3">
              <div
                className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 ${tone}`}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-ink-900 leading-snug line-clamp-2">
                  {e.subject ?? '(no subject)'}
                </div>
                <div className="text-xs text-ink-500 truncate mt-0.5">
                  {e.sender_name ?? e.sender}
                </div>
              </div>
            </li>
          )
        })}
        {upcoming.length === 0 && (
          <li className="text-sm text-ink-500 py-4 text-center">
            No upcoming interviews or offers in the inbox right now.
          </li>
        )}
      </ul>

      <div className="mt-4 pt-3 border-t border-cream-200 text-[11px] text-ink-500 leading-relaxed">
        Derived from inbox classifications. Microsoft Graph / Google Calendar
        sync lands in M4.
      </div>
    </Card>
  )
}
