import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Empty, PageHeader, Spinner } from '../../components/ui'
import { WaitlistOffers } from '../../components/WaitlistOffers'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dayLabel, money, relativeDays, timeLabel } from '../../lib/format'
import type { Booking, Membership, Notification } from '../../lib/types'

export function MemberHome() {
  const user = useAuth((s) => s.user)
  const qc = useQueryClient()
  const bookings = useQuery({ queryKey: ['my-bookings'], queryFn: () => api<Booking[]>('/me/bookings') })
  const membership = useQuery({ queryKey: ['my-membership'], queryFn: () => api<Membership | null>('/me/membership') })
  const notes = useQuery({ queryKey: ['notifications'], queryFn: () => api<Notification[]>('/me/notifications'), refetchInterval: 20_000 })
  const cancel = useMutation({
    mutationFn: (id: number) => api(`/bookings/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-bookings'] }),
  })
  const unread = (notes.data ?? []).filter((n) => !n.read)

  return (
    <div>
      <PageHeader
        title={`Hi, ${user?.full_name.split(' ')[0]}`}
        sub={`NTRP ${user?.skill_level.toFixed(1)}`}
        action={
          <Link to="/app/book">
            <Button>Book a court</Button>
          </Link>
        }
      />
      <WaitlistOffers />
      {unread.filter((n) => n.kind !== 'waitlist_offer').length > 0 && (
        <div className="mb-4 space-y-2">
          {unread
            .filter((n) => n.kind !== 'waitlist_offer')
            .slice(0, 3)
            .map((n) => (
            <Card key={n.id} className="border-ball bg-ball-soft p-4">
              <div className="font-bold">{n.title}</div>
              {n.body && <div className="text-sm">{n.body}</div>}
              {n.link && (
                <Link to={n.link} className="mt-1 inline-block text-sm font-semibold text-court-700">
                  Open →
                </Link>
              )}
            </Card>
          ))}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-3 font-bold">Your upcoming bookings</h2>
          {bookings.isLoading ? (
            <Spinner />
          ) : !bookings.data?.length ? (
            <Empty title="Nothing booked">
              <Link to="/app/book" className="font-semibold text-court-700">
                Find a court →
              </Link>
            </Empty>
          ) : (
            <ul className="divide-y divide-line">
              {bookings.data.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <div className="font-semibold">
                      {dayLabel(b.start_at)} · {timeLabel(b.start_at)}
                    </div>
                    <div className="text-sm text-muted">
                      {b.court_name}
                      {b.coach_name && ` · lesson with ${b.coach_name}`}
                      {b.type === 'match' && ` · match vs ${b.players.filter((p) => p.id !== user?.id).map((p) => p.full_name).join(', ')}`}
                      {' · '}
                      {money(b.price)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {b.type !== 'casual' && <Badge className="capitalize">{b.type}</Badge>}
                    <Button size="sm" variant="ghost" onClick={() => cancel.mutate(b.id)} disabled={cancel.isPending}>
                      Cancel
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-4">
          <Card>
            <h2 className="mb-2 font-bold">Membership</h2>
            {membership.data ? (
              <div className="text-sm">
                <div className="font-display text-xl font-bold">{membership.data.plan.name}</div>
                <div className="text-muted">
                  {membership.data.plan.court_discount_pct}% off courts · renews {membership.data.end_date}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted">No active membership. Ask at the front desk about plans.</p>
            )}
          </Card>
          <Link to="/app/qr" className="block">
            <Card className="bg-court-800 text-white">
              <div className="font-bold">Check-in QR code</div>
              <div className="text-sm text-court-100">Show it at the front desk tablet →</div>
            </Card>
          </Link>
          {(notes.data ?? []).filter((n) => n.read).length > 0 && (
            <Card>
              <h2 className="mb-2 font-bold">Recent updates</h2>
              <ul className="space-y-1 text-sm">
                {(notes.data ?? [])
                  .filter((n) => n.read)
                  .slice(0, 5)
                  .map((n) => (
                    <li key={n.id} className="flex justify-between gap-2">
                      <span>{n.title}</span>
                      <span className="shrink-0 text-muted">{relativeDays(n.created_at.slice(0, 19))}</span>
                    </li>
                  ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
      {unread.length > 0 && <MarkRead />}
    </div>
  )
}

function MarkRead() {
  const qc = useQueryClient()
  const read = useMutation({
    mutationFn: () => api('/me/notifications/read', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
  return (
    <button className="mt-4 text-xs font-semibold text-muted hover:text-ink" onClick={() => read.mutate()}>
      Mark updates as read
    </button>
  )
}
