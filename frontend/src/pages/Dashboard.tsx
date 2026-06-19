import { useQuery } from '@tanstack/react-query'
import { Briefcase, Mail, Users } from 'lucide-react'
import { fetchOverview } from '../lib/api'
import { AgentBar } from '../components/AgentBar'
import { TopBar } from '../components/TopBar'
import { StatCounts } from '../components/StatCounts'
import { CalendarCard } from '../components/CalendarCard'
import { TopJobsCard } from '../components/TopJobsCard'
import { UrgentEmailsCard } from '../components/UrgentEmailsCard'

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['overview'],
    queryFn: fetchOverview,
  })

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-ink-500">
        Loading dashboard…
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center text-ink-700">
        <div className="bg-white rounded-3xl border border-cream-200 p-8 max-w-md">
          <h2 className="text-lg font-semibold mb-2">Backend unreachable</h2>
          <p className="text-sm text-ink-500">
            Make sure FastAPI is running on <code>127.0.0.1:8000</code>:
          </p>
          <pre className="bg-cream-100 rounded-xl p-3 mt-3 text-xs">
            cd backend{'\n'}venv/bin/uvicorn main:app --reload
          </pre>
        </div>
      </div>
    )
  }

  const { user, counts, top_jobs, urgent_emails } = data

  return (
    <div className="min-h-screen p-6 lg:p-10">
      <div className="max-w-[1480px] mx-auto">
        <TopBar />

        {/* Welcome row + at-a-glance counts */}
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6 mb-8">
          <h1 className="text-5xl font-semibold tracking-tight text-ink-900 leading-none">
            Welcome back, {user.name.split(' ')[0]}
          </h1>
          <StatCounts
            items={[
              {
                value: counts.jobs_sponsors,
                label: 'Sponsor-friendly jobs',
                icon: <Briefcase className="h-4 w-4" />,
              },
              {
                value: counts.jobs_unique_companies,
                label: 'Companies',
                icon: <Users className="h-4 w-4" />,
              },
              {
                value: counts.emails_unread,
                label: 'Unread emails',
                icon: <Mail className="h-4 w-4" />,
              },
            ]}
          />
        </div>

        {/* Master Agent — natural-language entry to the M5 LangGraph */}
        <AgentBar />

        {/* 3-column grid; items-start keeps side cards content-sized */}
        <div className="grid grid-cols-12 gap-6 items-start">
          {/* Left rail — secondary cards stack vertically */}
          <div className="col-span-12 lg:col-span-3 space-y-6">
            <CalendarCard emails={urgent_emails} />
          </div>

          {/* Primary surface — the daily job feed */}
          <div className="col-span-12 lg:col-span-6">
            <TopJobsCard jobs={top_jobs} />
          </div>

          {/* Right rail — inbox priority */}
          <div className="col-span-12 lg:col-span-3 space-y-6">
            <UrgentEmailsCard emails={urgent_emails} />
          </div>
        </div>
      </div>
    </div>
  )
}
