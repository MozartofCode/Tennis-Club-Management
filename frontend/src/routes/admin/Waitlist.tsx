import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Badge, Card, Empty, PageHeader, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { dayLabel, hourLabel, money, timeLabel } from '../../lib/format'
import type { WaitlistEntry } from '../../lib/types'

interface Queue {
  entries: WaitlistEntry[]
  filled_30d: number
  offers_30d: number
  expired_30d: number
}

export function Waitlist() {
  const q = useQuery({ queryKey: ['waitlist'], queryFn: () => api<Queue>('/waitlist'), refetchInterval: 20_000 })
  if (q.isLoading || !q.data) return <Spinner />
  const groups = new Map<string, WaitlistEntry[]>()
  for (const e of q.data.entries) {
    const key = `${e.date}|${e.start_hour}|${e.end_hour}`
    groups.set(key, [...(groups.get(key) ?? []), e])
  }
  const waiting = q.data.entries.filter((e) => e.status === 'waiting').length
  return (
    <div>
      <PageHeader
        title="Waitlist"
        sub="When a booking is cancelled, the slot is offered automatically to the best-placed member with a short hold. Nobody has to phone around."
      />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Waiting now" value={waiting} />
        <Stat label="On hold right now" value={q.data.entries.filter((e) => e.status === 'offered').length} />
        <Stat label="Slots refilled (30 days)" value={q.data.filled_30d} sub="booked straight from the waitlist" tone="good" />
        <Stat label="Offers that expired" value={q.data.expired_30d} sub={`of ${q.data.offers_30d} offers`} />
      </div>
      {groups.size === 0 ? (
        <Empty title="Nobody is waiting">Members can join the waitlist from the booking page when an hour is full.</Empty>
      ) : (
        <div className="space-y-3">
          {[...groups.entries()].map(([key, list]) => {
            const [d, s, e] = key.split('|')
            return (
              <Card key={key}>
                <h2 className="mb-2 font-bold">
                  {dayLabel(`${d}T00:00:00`)} · {hourLabel(Number(s))}
                  {s !== e && `-${hourLabel(Number(e) + 1)}`}
                </h2>
                <ol className="space-y-2">
                  {list.map((entry, i) => (
                    <li key={entry.id} className="flex flex-wrap items-start justify-between gap-2 rounded-xl bg-paper p-3 text-sm">
                      <div>
                        <div className="font-semibold">
                          {i + 1}.{' '}
                          <Link to={`/admin/members/${entry.user_id}`} className="text-court-800 hover:underline">
                            {entry.member_name}
                          </Link>
                          <span className="ml-2 font-normal text-muted">score {entry.priority_score}</span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {entry.priority_reasons.map((r) => (
                            <Badge key={r} tone={r.includes('churn') ? 'clay' : r.includes('(-') ? 'neutral' : 'green'}>
                              {r}
                            </Badge>
                          ))}
                          {entry.priority_reasons.length === 0 && <span className="text-xs text-muted">Just joined</span>}
                        </div>
                      </div>
                      {entry.status === 'offered' ? (
                        <Badge tone="ball">
                          Holding {entry.offer_court_name} {entry.offer_start_at && timeLabel(entry.offer_start_at)} · {money(entry.offer_price ?? 0)} until{' '}
                          {entry.offer_expires_at && timeLabel(entry.offer_expires_at)}
                        </Badge>
                      ) : (
                        <Badge>Waiting</Badge>
                      )}
                    </li>
                  ))}
                </ol>
              </Card>
            )
          })}
        </div>
      )}
      <p className="mt-4 text-xs text-muted">
        Ranking: membership tier, time waiting, churn risk (members at risk of leaving get a boost), fewer recent offers, and an exact time match. Each hold
        lasts the club's hold time (15 minutes by default); if it isn't taken, the next member is offered the slot.
      </p>
    </div>
  )
}
