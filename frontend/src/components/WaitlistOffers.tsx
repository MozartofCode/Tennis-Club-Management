import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { dayLabel, hourLabel, money, parseLocal, timeLabel } from '../lib/format'
import type { WaitlistEntry } from '../lib/types'
import { Badge, Button, Card, ErrorNote } from './ui'

function useNow(ms: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(t)
  }, [ms])
  return now
}

export function WaitlistOffers() {
  const qc = useQueryClient()
  const now = useNow(1000)
  const mine = useQuery({ queryKey: ['my-waitlist'], queryFn: () => api<WaitlistEntry[]>('/waitlist/mine'), refetchInterval: 15_000 })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['my-waitlist'] })
    qc.invalidateQueries({ queryKey: ['my-bookings'] })
    qc.invalidateQueries({ queryKey: ['availability'] })
  }
  const accept = useMutation({ mutationFn: (id: number) => api(`/waitlist/${id}/accept`, { method: 'POST' }), onSuccess: refresh })
  const decline = useMutation({ mutationFn: (id: number) => api(`/waitlist/${id}/decline`, { method: 'POST' }), onSuccess: refresh })
  const leave = useMutation({ mutationFn: (id: number) => api(`/waitlist/${id}`, { method: 'DELETE' }), onSuccess: refresh })
  const entries = mine.data ?? []
  if (!entries.length) return null
  const offers = entries.filter((e) => e.status === 'offered')
  const waiting = entries.filter((e) => e.status === 'waiting')
  return (
    <div className="mb-4 space-y-3">
      {offers.map((e) => {
        const left = e.offer_expires_at ? Math.max(0, parseLocal(e.offer_expires_at).getTime() - now) : 0
        const mm = Math.floor(left / 60000)
        const ss = Math.floor((left % 60000) / 1000)
        return (
          <Card key={e.id} className="border-2 border-ball bg-ball-soft">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <Badge tone="green">From your waitlist</Badge>
                <div className="mt-1 font-display text-xl font-bold">
                  {e.offer_court_name} · {e.offer_start_at && `${dayLabel(e.offer_start_at)}, ${timeLabel(e.offer_start_at)}`}
                </div>
                <div className="text-sm">
                  Held for you for <b>{mm}:{String(ss).padStart(2, '0')}</b> · {money(e.offer_price ?? 0)}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => decline.mutate(e.id)} disabled={decline.isPending}>
                  No thanks
                </Button>
                <Button onClick={() => accept.mutate(e.id)} disabled={accept.isPending || left === 0}>
                  Book it
                </Button>
              </div>
            </div>
            <ErrorNote error={accept.error} />
          </Card>
        )
      })}
      {waiting.length > 0 && (
        <Card className="p-4">
          <div className="mb-1 text-sm font-semibold">You're on the waitlist</div>
          <ul className="space-y-1 text-sm">
            {waiting.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2">
                <span>
                  {dayLabel(`${e.date}T00:00:00`)}, {hourLabel(e.start_hour)}
                  {e.end_hour !== e.start_hour && `-${hourLabel(e.end_hour + 1)}`}
                </span>
                <button className="text-xs font-semibold text-muted hover:text-clay-600" onClick={() => leave.mutate(e.id)}>
                  Leave
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">We'll notify you and hold the court if one opens up.</p>
        </Card>
      )}
    </div>
  )
}
