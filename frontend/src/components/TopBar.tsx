import { Bell, Settings, User } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'

interface NavItem {
  label: string
  to: string | null   // null = not yet routable (placeholder)
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', to: '/' },
  { label: 'Jobs', to: null },
  { label: 'Resume', to: '/resume' },
  { label: 'Emails', to: null },
  { label: 'Calendar', to: null },
  { label: 'Agent', to: null },
]

export function TopBar() {
  return (
    <header className="flex items-center justify-between gap-4 mb-8">
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="h-10 px-5 rounded-full bg-white border border-cream-200 flex items-center hover:bg-cream-50 transition-colors"
        >
          <span className="font-semibold tracking-tight text-ink-900">Nexus</span>
        </Link>
      </div>

      <nav className="flex items-center bg-cream-50/80 border border-cream-200 rounded-full p-1 shadow-sm">
        {NAV_ITEMS.map((item) =>
          item.to ? (
            <NavLink
              key={item.label}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `px-4 py-1.5 text-sm rounded-full transition-colors ${
                  isActive
                    ? 'bg-ink-900 text-white font-medium'
                    : 'text-ink-500 hover:text-ink-900'
                }`
              }
            >
              {item.label}
            </NavLink>
          ) : (
            <button
              key={item.label}
              disabled
              className="px-4 py-1.5 text-sm rounded-full text-ink-500/50 cursor-not-allowed"
              title="Coming soon"
            >
              {item.label}
            </button>
          ),
        )}
      </nav>

      <div className="flex items-center gap-2">
        <button className="h-10 px-4 rounded-full bg-white border border-cream-200 flex items-center gap-2 text-sm text-ink-700 hover:bg-cream-50">
          <Settings className="h-4 w-4" />
          Setting
        </button>
        <button className="h-10 w-10 rounded-full bg-white border border-cream-200 flex items-center justify-center relative">
          <Bell className="h-4 w-4 text-ink-700" />
          <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-amber-strong" />
        </button>
        <button className="h-10 w-10 rounded-full bg-white border border-cream-200 flex items-center justify-center">
          <User className="h-4 w-4 text-ink-700" />
        </button>
      </div>
    </header>
  )
}
