import { Card } from './Card'
import { GraduationCap } from 'lucide-react'

interface Props {
  name: string
  email: string
  resumeLabel: string | null
  resumeVersion: number | null
  sectionsCount: number
}

export function ResumeProfileCard({
  name,
  email,
  resumeLabel,
  resumeVersion,
  sectionsCount,
}: Props) {
  return (
    <Card className="relative overflow-hidden flex flex-col justify-between h-full min-h-[260px] bg-gradient-to-br from-amber-soft via-cream-100 to-cream-200">
      {/* Subtle background "photo" stand-in — a soft circle since this is a CLI-only project portrait */}
      <div className="absolute -top-10 -right-10 h-48 w-48 rounded-full bg-amber-brand/40 blur-2xl" />
      <div className="absolute bottom-0 right-0 h-32 w-32 rounded-full bg-ink-900/10 blur-xl" />

      <div className="relative flex items-center gap-3">
        <div className="h-12 w-12 rounded-2xl bg-ink-900 text-white flex items-center justify-center font-semibold text-lg shrink-0">
          {name.split(' ').map((s) => s[0]).join('').slice(0, 2).toUpperCase()}
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-ink-500">Active profile</div>
          <div className="text-lg font-semibold leading-tight">{name}</div>
        </div>
      </div>

      <div className="relative space-y-2">
        <div className="text-sm text-ink-700">{email}</div>
        <div className="flex items-center gap-2 text-sm text-ink-700">
          <GraduationCap className="h-4 w-4" />
          <span>{resumeLabel ?? 'Master Resume'} · v{resumeVersion ?? 1}</span>
        </div>
        <div className="inline-flex items-center px-3 py-1 rounded-full bg-white/80 text-xs text-ink-700">
          {sectionsCount} embedded sections
        </div>
      </div>
    </Card>
  )
}
