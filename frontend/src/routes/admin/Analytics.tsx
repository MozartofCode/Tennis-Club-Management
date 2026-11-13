import { useQuery } from '@tanstack/react-query'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, PageHeader, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { hourLabel, money, pct } from '../../lib/format'

interface Analytics {
  weekly: { week: string; revenue: number; bookings: number; utilization: number; visits: number; active_members: number }[]
  by_hour: { hour: number; weekday: number; weekend: number; weekday_peak: boolean; weekend_peak: boolean }[]
  last_30: { revenue: number; bookings: number; cancel_rate: number; no_show_rate: number; avg_peak_price: number; avg_offpeak_price: number; lesson_share: number }
  members: { total: number; active_memberships: number; new_30d: number; renewal_rate_30d: number | null; lapsed_30d: number }
  ai: {
    pricing_mode: string
    waitlist_refills_30d: number
    waitlist_revenue_30d: number
    waiting_now: number
    match_bookings_30d: number
    match_offpeak_share: number | null
    league_matches_30d: number
    offers_30d: Record<string, number>
    risk: Record<string, number>
  }
}

const shortWeek = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

export function AnalyticsPage() {
  const q = useQuery({ queryKey: ['analytics'], queryFn: () => api<Analytics>('/analytics?weeks=12') })
  if (q.isLoading || !q.data) return <Spinner />
  const { weekly, by_hour, last_30, members, ai } = q.data
  const offersSent = (ai.offers_30d.sent ?? 0) + (ai.offers_30d.redeemed ?? 0)
  return (
    <div>
      <PageHeader title="Analytics" sub="The last 12 weeks, and what the AI features did in the last 30 days." />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Revenue (30 days)" value={money(Math.round(last_30.revenue))} sub={`${last_30.bookings} bookings`} />
        <Stat label="Active memberships" value={members.active_memberships} sub={`${members.new_30d} new members this month`} />
        <Stat
          label="Renewal rate (30 days)"
          value={members.renewal_rate_30d === null ? '-' : pct(members.renewal_rate_30d)}
          sub={`${members.lapsed_30d} lapsed`}
          tone={members.lapsed_30d ? 'bad' : 'good'}
        />
        <Stat label="Cancellations / no-shows" value={`${pct(last_30.cancel_rate)} / ${pct(last_30.no_show_rate)}`} />
      </div>

      <h2 className="mb-2 mt-6 text-lg font-bold">AI at work, last 30 days</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Slots refilled from waitlist" value={ai.waitlist_refills_30d} sub={`${money(ai.waitlist_revenue_30d)} that would have sat empty`} tone="good" />
        <Stat
          label="Matches booked by matchmaking"
          value={ai.match_bookings_30d}
          sub={ai.match_offpeak_share === null ? 'none yet' : `${pct(ai.match_offpeak_share)} in off-peak hours`}
          tone="good"
        />
        <Stat label="Retention offers sent" value={offersSent} sub={`${ai.offers_30d.redeemed ?? 0} claimed · ${ai.risk.high ?? 0} members high risk now`} />
        <Stat
          label="Peak vs off-peak price"
          value={`${money(last_30.avg_peak_price)} / ${money(last_30.avg_offpeak_price)}`}
          sub={`dynamic pricing: ${ai.pricing_mode}`}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-bold">Weekly revenue</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <AreaChart data={weekly.map((w) => ({ ...w, label: shortWeek(w.week) }))}>
                <CartesianGrid vertical={false} stroke="#e3e2da" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={48} tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v) => money(Number(v))} />
                <Area dataKey="revenue" name="Revenue" stroke="#1a5233" fill="#a9d3b6" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <h2 className="mb-3 font-bold">Members coming in each week</h2>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={weekly.map((w) => ({ ...w, label: shortWeek(w.week) }))}>
                <CartesianGrid vertical={false} stroke="#e3e2da" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={36} />
                <Tooltip />
                <Bar dataKey="active_members" name="Members who visited" fill="#1a5233" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <h2 className="font-bold">When courts are used (last 8 weeks)</h2>
          <p className="mb-3 text-sm text-muted">Share of courts booked by hour. Tall peaks and empty valleys are where pricing and matchmaking help most.</p>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={by_hour.map((h) => ({ hour: hourLabel(h.hour), Weekdays: Math.round(h.weekday * 100), Weekends: Math.round(h.weekend * 100) }))}>
                <CartesianGrid vertical={false} stroke="#e3e2da" />
                <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                <YAxis unit="%" tick={{ fontSize: 11 }} width={40} domain={[0, 100]} />
                <Tooltip formatter={(v) => `${v}%`} />
                <Legend />
                <Bar dataKey="Weekdays" fill="#2f7d4f" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Weekends" fill="#c8562a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  )
}
