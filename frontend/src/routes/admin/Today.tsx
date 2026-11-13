import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Empty, PageHeader, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { dateKey, money, parseLocal, timeLabel } from '../../lib/format'
import type { Availability, Booking, CheckInRow } from '../../lib/types'
import { useClub } from '../../lib/queries'

export function Today() {
  const [now] = useState(() => new Date())
  const key = dateKey(now)
  const club = useClub()
  const bookings = useQuery({ queryKey: ['bookings', key], queryFn: () => api<Booking[]>(`/bookings?day=${key}`), refetchInterval: 30_000 })
  const grid = useQuery({ queryKey: ['availability', key], queryFn: () => api<Availability>(`/availability?day=${key}`) })
  const checkins = useQuery({ queryKey: ['checkins', key], queryFn: () => api<CheckInRow[]>(`/checkin?day=${key}`), refetchInterval: 15_000 })

  if (bookings.isLoading || grid.isLoading || club.isLoading) return <Spinner />
  const list = bookings.data ?? []
  const capacity = (grid.data?.courts.length ?? 0) * (grid.data?.hours.length ?? 0)
  const revenue = list.reduce((s, b) => s + b.price, 0)
  const unpaid = list.filter((b) => !b.paid && b.status !== 'cancelled')
  const upcoming = list.filter((b) => parseLocal(b.end_at) > now).slice(0, 10)

  return (
    <div>
      <PageHeader
        title={`Good ${now.getHours() < 12 ? 'morning' : now.getHours() < 18 ? 'afternoon' : 'evening'}`}
        sub={`${club.data?.name} · ${now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}`}
        action={
          <Link to="/kiosk" target="_blank">
            <Button variant="ball">Open check-in kiosk ↗</Button>
          </Link>
        }
      />
      {club.data && !club.data.setup_complete && (
        <Card className="mb-4 flex flex-wrap items-center justify-between gap-3 border-ball bg-ball-soft">
          <div>
            <div className="font-bold">Finish setting up your club</div>
            <div className="text-sm text-muted">Add courts, prices, coaches and your members. About 10 minutes.</div>
          </div>
          <Link to="/admin/setup">
            <Button>Continue setup</Button>
          </Link>
        </Card>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Court-hours booked" value={`${list.length}/${capacity}`} sub={`${capacity ? Math.round((list.length / capacity) * 100) : 0}% utilization`} />
        <Stat label="Check-ins today" value={checkins.data?.length ?? 0} />
        <Stat label="Booked revenue" value={money(revenue, club.data?.currency)} />
        <Stat label="Unpaid bookings" value={unpaid.length} sub={unpaid.length ? money(unpaid.reduce((s, b) => s + b.price, 0)) + ' to collect' : 'All settled'} tone={unpaid.length ? 'bad' : 'good'} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">Up next</h2>
            <Link to="/admin/calendar" className="text-sm font-semibold text-court-700">
              Full calendar →
            </Link>
          </div>
          {upcoming.length === 0 ? (
            <Empty title="Nothing else booked today" />
          ) : (
            <ul className="divide-y divide-line text-sm">
              {upcoming.map((b) => (
                <li key={b.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="w-16 font-semibold">{timeLabel(b.start_at)}</span>
                    <span>
                      {b.title || b.players.map((p) => p.full_name).join(', ') || b.booker_name}
                      <span className="text-muted"> · {b.court_name}</span>
                    </span>
                  </div>
                  <div className="flex gap-1">
                    {b.type !== 'casual' && <Badge className="capitalize">{b.type}</Badge>}
                    {b.checked_in && <Badge tone="green">Here</Badge>}
                    {!b.paid && <Badge tone="clay">Unpaid</Badge>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h2 className="mb-3 font-bold">Latest check-ins</h2>
          {(checkins.data ?? []).length === 0 && <p className="text-sm text-muted">No one yet.</p>}
          <ul className="space-y-1 text-sm">
            {(checkins.data ?? []).slice(0, 8).map((c) => (
              <li key={c.id} className="flex justify-between">
                <span>{c.member_name}</span>
                <span className="text-muted">{timeLabel(c.created_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
