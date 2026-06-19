import type { ReactNode } from 'react'

/** Big right-aligned number triplet, like the "78 Employe / 56 Hirings / 203 Projects"
 *  row in the Crextio reference. */
export interface StatItem {
  value: number | string
  label: string
  icon: ReactNode
}

export function StatCounts({ items }: { items: StatItem[] }) {
  return (
    <div className="flex items-center gap-10">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-cream-200/70 flex items-center justify-center text-ink-700">
            {it.icon}
          </div>
          <div>
            <div className="text-3xl font-semibold leading-none tabular">{it.value}</div>
            <div className="text-xs text-ink-500 mt-1">{it.label}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
