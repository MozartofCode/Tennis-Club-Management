import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PriceBreakdown } from '../../components/PriceBreakdown'
import { Button, ErrorNote, Field, Modal, PageHeader, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dateKey, dayLabel, hourLabel, money, timeLabel } from '../../lib/format'
import type { Availability, Cell, Coach } from '../../lib/types'

function nextDays(n: number): Date[] {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() + i)
    return d
  })
}

export function Book() {
  const [day, setDay] = useState(() => nextDays(1)[0])
  const key = dateKey(day)
  const grid = useQuery({ queryKey: ['availability', key], queryFn: () => api<Availability>(`/availability?day=${key}`) })
  const [pick, setPick] = useState<Cell | null>(null)
  const [full, setFull] = useState<number | null>(null)

  const cellsByHour = new Map<number, Cell[]>()
  for (const c of grid.data?.cells ?? []) cellsByHour.set(c.hour, [...(cellsByHour.get(c.hour) ?? []), c])
  const courtName = (id: number) => grid.data?.courts.find((c) => c.id === id)?.name ?? ''
  const prices = (grid.data?.cells ?? []).filter((c) => c.status === 'free').map((c) => c.price)
  const cheapest = prices.length ? Math.min(...prices) : 0

  return (
    <div>
      <PageHeader title="Book a court" sub="Prices change with demand. Quieter hours are cheaper." />
      <div className="-mx-4 mb-5 flex gap-2 overflow-x-auto px-4 pb-1">
        {nextDays(14).map((d) => (
          <button
            key={d.toISOString()}
            onClick={() => setDay(d)}
            className={clsx(
              'flex min-w-[64px] flex-col items-center rounded-xl border px-3 py-2 text-sm',
              dateKey(d) === key ? 'border-court-800 bg-court-800 text-white' : 'border-line bg-white',
            )}
          >
            <span className="text-xs">{d.toLocaleDateString('en-US', { weekday: 'short' })}</span>
            <span className="font-bold">{d.getDate()}</span>
          </button>
        ))}
      </div>
      {grid.isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-2">
          {grid.data?.hours.map((h) => {
            const cells = cellsByHour.get(h) ?? []
            const free = cells.filter((c) => c.status === 'free')
            const mine = cells.find((c) => c.status === 'mine')
            const past = cells.every((c) => c.status === 'past')
            const best = free.sort((a, b) => a.price - b.price)[0]
            if (past) return null
            return (
              <div key={h} className="flex items-center gap-3 rounded-2xl border border-line bg-white p-3">
                <div className="w-14 font-display text-lg font-bold">{hourLabel(h)}</div>
                <div className="flex flex-1 flex-wrap gap-1.5">
                  {mine && <span className="rounded-lg bg-ball px-2 py-1 text-xs font-bold text-court-900">Your booking · {courtName(mine.court_id)}</span>}
                  {!mine &&
                    free.map((c) => (
                      <button key={c.court_id} onClick={() => setPick(c)} className="rounded-lg border border-court-200 bg-court-50 px-2 py-1 text-xs font-semibold text-court-800 hover:bg-court-100">
                        {courtName(c.court_id)}
                      </button>
                    ))}
                  {!mine && free.length === 0 && (
                    <button onClick={() => setFull(h)} className="rounded-lg border border-dashed border-line px-2 py-1 text-xs font-semibold text-muted hover:text-ink">
                      Full · join waitlist
                    </button>
                  )}
                </div>
                {best && (
                  <div className="text-right">
                    <div className={clsx('font-bold', best.price <= cheapest && 'text-court-600')}>{money(best.price)}</div>
                    {best.breakdown.some((b) => b.pct < 0 && !b.label.includes('member')) && <div className="text-xs text-court-600">off-peak deal</div>}
                    {best.breakdown.some((b) => b.pct > 0) && <div className="text-xs text-clay-600">busy hour</div>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      {pick && <ConfirmBooking cell={pick} court={courtName(pick.court_id)} onClose={() => setPick(null)} dayKey={key} />}
      {full !== null && <WaitlistJoin day={key} hour={full} onClose={() => setFull(null)} />}
    </div>
  )
}

function ConfirmBooking({ cell, court, onClose, dayKey }: { cell: Cell; court: string; onClose: () => void; dayKey: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [coachId, setCoachId] = useState('')
  const coaches = useQuery({ queryKey: ['coaches'], queryFn: () => api<Coach[]>('/club/coaches') })
  const coach = coaches.data?.find((c) => String(c.id) === coachId)
  const book = useMutation({
    mutationFn: () => api('/bookings', { body: { court_id: cell.court_id, start_at: cell.start_at, coach_id: coachId ? Number(coachId) : null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['availability', dayKey] })
      qc.invalidateQueries({ queryKey: ['my-bookings'] })
      navigate('/app')
    },
  })
  return (
    <Modal open onClose={onClose} title={`${court} · ${dayLabel(cell.start_at)}, ${timeLabel(cell.start_at)}`}>
      <div className="space-y-4">
        <PriceBreakdown base={cell.base_price} price={cell.price} lines={cell.breakdown} />
        <Field label="Add a coach (optional)">
          <Select value={coachId} onChange={(e) => setCoachId(e.target.value)}>
            <option value="">Just the court</option>
            {(coaches.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                Lesson with {c.user.full_name} (+{money(c.hourly_rate)})
              </option>
            ))}
          </Select>
        </Field>
        {coach && (
          <p className="text-sm text-muted">
            Total with lesson: <b className="text-ink">{money(cell.price + coach.hourly_rate)}</b>
          </p>
        )}
        <p className="text-xs text-muted">Pay at the front desk when you arrive.</p>
        <ErrorNote error={book.error} />
        <Button className="w-full" disabled={book.isPending} onClick={() => book.mutate()}>
          Confirm booking
        </Button>
      </div>
    </Modal>
  )
}

export function WaitlistJoin({ day, hour, onClose }: { day: string; hour: number; onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title="This hour is full">
      <p className="text-sm text-muted">
        All courts are booked at {hourLabel(hour)} on {dayLabel(`${day}T00:00:00`)}. Pick another time for now.
      </p>
      <Button className="mt-4 w-full" variant="secondary" onClick={onClose}>
        OK
      </Button>
    </Modal>
  )
}
