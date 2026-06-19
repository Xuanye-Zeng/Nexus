import { Calendar, DollarSign, Mail, MessageSquare, Link as LinkIcon } from 'lucide-react'
import type { UrgentEmail } from '../lib/api'
import { DarkCard } from './Card'

const CATEGORY_ICON: Record<string, typeof Mail> = {
  interview: Calendar,
  offer: DollarSign,
  recruiter: MessageSquare,
  application_confirmation: LinkIcon,
}

interface Props {
  emails: UrgentEmail[]
}

export function UrgentEmailsCard({ emails }: Props) {
  return (
    <DarkCard className="flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-medium">Inbox priority</h3>
        <span className="text-sm text-ink-300">
          {emails.length}/{emails.length}
        </span>
      </div>

      <ul className="space-y-3 flex-1">
        {emails.map((e) => {
          const Icon = CATEGORY_ICON[e.category ?? ''] ?? Mail
          return (
            <li key={e.id} className="flex items-start gap-3">
              <div className="h-9 w-9 rounded-full bg-white text-ink-900 flex items-center justify-center shrink-0">
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">
                  {e.subject ?? '(no subject)'}
                </div>
                <div className="text-xs text-ink-300 truncate">
                  {e.sender_name ?? e.sender} · {e.category ?? '—'}
                </div>
              </div>
              <span
                className={`h-2 w-2 rounded-full shrink-0 mt-3 ${
                  (e.importance_score ?? 0) >= 5
                    ? 'bg-amber-brand'
                    : (e.importance_score ?? 0) >= 4
                      ? 'bg-amber-soft'
                      : 'bg-ink-500'
                }`}
                title={`importance ${e.importance_score}`}
              />
            </li>
          )
        })}
        {emails.length === 0 && (
          <li className="text-sm text-ink-300 py-8 text-center">
            No urgent emails. Inbox zero — nice.
          </li>
        )}
      </ul>
    </DarkCard>
  )
}
