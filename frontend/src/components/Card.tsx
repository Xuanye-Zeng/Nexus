import type { ReactNode } from 'react'

/** White card — the default surface. */
export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`bg-white rounded-3xl border border-cream-200 p-6 ${className}`}
    >
      {children}
    </div>
  )
}

/** Black hero card (matches the Crextio onboarding-task panel). */
export function DarkCard({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`bg-ink-900 text-white rounded-3xl p-6 ${className}`}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  right,
}: {
  title: string
  right?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-base font-medium text-ink-900">{title}</h3>
      {right}
    </div>
  )
}
