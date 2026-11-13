import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PriceBreakdown } from '../../components/PriceBreakdown'
import { Badge, Button, ErrorNote, Field, Input, Modal, PageHeader, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dateKey, hourLabel, money, timeLabel } from '../../lib/format'
import type { Availability, Booking, Coach, MemberRow } from '../../lib/types'

const TYPE_STYLE: Record<Booking['type'], string> = {
  casual: 'bg-court-100 text-court-900 border-court-200',
  lesson: 'bg-sky-100 text-sky-900 border-sky-200',
  match: 'bg-ball-soft text-court-900 border-ball',
  clinic: 'bg-violet-100 text-violet-900 border-violet-200',
}

export function DateNav({ day, setDay }: { day: Date; setDay: (d: Date) => void }) {
  const shift = (n: number) => {
    const d = new Date(day)
    d.setDate(d.getDate() + n)
    setDay(d)
  }
  return (
    <div className="flex items-center gap-2">
      <Button size="sm" variant="secondary" onClick={() => shift(-1)} aria-label="Previous day">
        ←
      </Button>
      <input
        type="date"
        className="rounded-xl border border-line bg-white px-3 py-1.5 text-sm"
        value={dateKey(day)}
        onChange={(e) => e.target.value && setDay(new Date(`${e.target.value}T00:00:00`))}
      />
      <Button size="sm" variant="secondary" onClick={() => shift(1)} aria-label="Next day">
        →
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setDay(new Date())}>
        Today
      </Button>
    </div>
  )
}

export function Calendar() {
  const [day, setDay] = useState(() => new Date())
  const key = dateKey(day)
  const grid = useQuery({ queryKey: ['availability', key], queryFn: () => api<Availability>(`/availability?day=${key}`) })
  const bookings = useQuery({ queryKey: ['bookings', key], queryFn: () => api<Booking[]>(`/bookings?day=${key}`) })
  const [newSlot, setNewSlot] = useState<{ court_id: number; start_at: string; court: string } | null>(null)
  const [open, setOpen] = useState<Booking | null>(null)

  if (grid.isLoading || bookings.isLoading) return <Spinner />
  if (!grid.data) return null
  const byCell = new Map((bookings.data ?? []).map((b) => [`${b.court_id}-${Number(b.start_at.slice(11, 13))}`, b]))
  const cellFor = new Map(grid.data.cells.map((c) => [`${c.court_id}-${c.hour}`, c]))
  const total = grid.data.courts.length * grid.data.hours.length
  const used = bookings.data?.length ?? 0

  return (
    <div>
      <PageHeader
        title="Court calendar"
        sub={`${used} of ${total} court-hours booked (${total ? Math.round((used / total) * 100) : 0}%). Click an empty slot to book for a member.`}
        action={<DateNav day={day} setDay={setDay} />}
      />
      {grid.data.courts.length === 0 ? (
        <p className="text-sm text-muted">
          No courts yet. <Link className="font-semibold text-court-700" to="/admin/setup">Add courts in setup.</Link>
        </p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 w-16 bg-white p-2 text-left text-xs text-muted" />
                {grid.data.courts.map((c) => (
                  <th key={c.id} className="border-l border-line p-2 text-left font-semibold">
                    {c.name}
                    <div className="text-xs font-normal text-muted">
                      {c.surface} · {c.indoor ? 'indoor' : 'outdoor'}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.data.hours.map((h) => (
                <tr key={h} className="border-t border-line">
                  <td className="sticky left-0 z-10 bg-white p-2 text-xs font-semibold text-muted">{hourLabel(h)}</td>
                  {grid.data!.courts.map((c) => {
                    const b = byCell.get(`${c.id}-${h}`)
                    const cell = cellFor.get(`${c.id}-${h}`)
                    return (
                      <td key={c.id} className="h-14 border-l border-line p-1 align-top">
                        {b ? (
                          <button onClick={() => setOpen(b)} className={clsx('h-full w-full rounded-lg border px-2 py-1 text-left text-xs', TYPE_STYLE[b.type])}>
                            <div className="truncate font-semibold">{b.title || b.players.map((p) => p.full_name.split(' ')[0]).join(' vs ') || b.booker_name || 'Booked'}</div>
                            <div className="flex items-center gap-1 opacity-80">
                              {b.type !== 'casual' && <span className="capitalize">{b.type}</span>}
                              {b.checked_in && <span title="Checked in">✓</span>}
                              {!b.paid && <span className="font-bold text-clay-600">unpaid</span>}
                            </div>
                          </button>
                        ) : cell?.status === 'past' ? (
                          <div className="h-full rounded-lg bg-stone-50" />
                        ) : (
                          <button
                            onClick={() => setNewSlot({ court_id: c.id, start_at: cell!.start_at, court: c.name })}
                            className="group h-full w-full rounded-lg text-left text-xs text-muted hover:bg-court-50"
                          >
                            <span className="hidden px-2 group-hover:inline">+ {cell ? money(cell.price) : ''}</span>
                          </button>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {Object.entries(TYPE_STYLE).map(([t, cls]) => (
          <span key={t} className={clsx('rounded-full border px-2 py-0.5 capitalize', cls)}>
            {t}
          </span>
        ))}
      </div>
      {newSlot && <NewBookingModal slot={newSlot} onClose={() => setNewSlot(null)} dayKey={key} />}
      {open && <BookingModal booking={open} onClose={() => setOpen(null)} dayKey={key} />}
    </div>
  )
}

export function MemberPicker({ value, onChange }: { value: MemberRow | null; onChange: (m: MemberRow | null) => void }) {
  const [q, setQ] = useState('')
  const results = useQuery({
    queryKey: ['member-search', q],
    queryFn: () => api<MemberRow[]>(`/members?q=${encodeURIComponent(q)}`),
    enabled: q.length >= 2,
  })
  if (value)
    return (
      <div className="flex items-center justify-between rounded-xl border border-line px-3 py-2 text-sm">
        <span>
          <b>{value.full_name}</b> · NTRP {value.skill_level.toFixed(1)}
        </span>
        <button className="text-xs font-semibold text-court-700" onClick={() => onChange(null)}>
          Change
        </button>
      </div>
    )
  return (
    <div>
      <Input placeholder="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      {results.data && (
        <ul className="mt-1 max-h-48 overflow-y-auto rounded-xl border border-line">
          {results.data.slice(0, 8).map((m) => (
            <li key={m.id}>
              <button className="w-full px-3 py-2 text-left text-sm hover:bg-court-50" onClick={() => onChange(m)}>
                {m.full_name} <span className="text-muted">· {m.email}</span>
              </button>
            </li>
          ))}
          {results.data.length === 0 && <li className="px-3 py-2 text-sm text-muted">No matches</li>}
        </ul>
      )}
    </div>
  )
}

function NewBookingModal({ slot, onClose, dayKey }: { slot: { court_id: number; start_at: string; court: string }; onClose: () => void; dayKey: string }) {
  const qc = useQueryClient()
  const [member, setMember] = useState<MemberRow | null>(null)
  const [coachId, setCoachId] = useState('')
  const [title, setTitle] = useState('')
  const [type, setType] = useState('casual')
  const coaches = useQuery({ queryKey: ['coaches'], queryFn: () => api<Coach[]>('/club/coaches') })
  const book = useMutation({
    mutationFn: () =>
      api<Booking>('/bookings', {
        body: { court_id: slot.court_id, start_at: slot.start_at, member_id: member?.id, coach_id: coachId ? Number(coachId) : null, type, title: title || null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bookings', dayKey] })
      qc.invalidateQueries({ queryKey: ['availability', dayKey] })
      onClose()
    },
  })
  const needsMember = type !== 'clinic'
  return (
    <Modal open onClose={onClose} title={`${slot.court} · ${timeLabel(slot.start_at)}`}>
      <div className="space-y-4">
        <Field label="Type">
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="casual">Court booking</option>
            <option value="lesson">Private lesson</option>
            <option value="clinic">Group clinic</option>
          </Select>
        </Field>
        {needsMember && (
          <Field label="Member">
            <MemberPicker value={member} onChange={setMember} />
          </Field>
        )}
        {type !== 'casual' && (
          <Field label="Coach">
            <Select value={coachId} onChange={(e) => setCoachId(e.target.value)}>
              <option value="">Choose a coach</option>
              {(coaches.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.user.full_name} ({money(c.hourly_rate)}/hr)
                </option>
              ))}
            </Select>
          </Field>
        )}
        {type === 'clinic' && (
          <Field label="Clinic name">
            <Input placeholder="e.g. 3.0 Doubles Drills" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
        )}
        <ErrorNote error={book.error} />
        <Button className="w-full" disabled={book.isPending || (needsMember && !member) || (type !== 'casual' && !coachId)} onClick={() => book.mutate()}>
          Book
        </Button>
      </div>
    </Modal>
  )
}

function BookingModal({ booking, onClose, dayKey }: { booking: Booking; onClose: () => void; dayKey: string }) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['bookings', dayKey] })
    qc.invalidateQueries({ queryKey: ['availability', dayKey] })
  }
  const patch = useMutation({
    mutationFn: (body: object) => api<Booking>(`/bookings/${booking.id}`, { method: 'PATCH', body }),
    onSuccess: () => {
      refresh()
      onClose()
    },
  })
  const cancel = useMutation({
    mutationFn: () => api<Booking>(`/bookings/${booking.id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      refresh()
      qc.invalidateQueries({ queryKey: ['waitlist'] })
      onClose()
    },
  })
  return (
    <Modal open onClose={onClose} title={`${booking.court_name} · ${timeLabel(booking.start_at)}`}>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge tone="green" className="capitalize">
            {booking.type}
          </Badge>
          <Badge tone={booking.paid ? 'green' : 'clay'}>{booking.paid ? 'Paid' : 'Unpaid'}</Badge>
          {booking.checked_in && <Badge tone="blue">Checked in</Badge>}
          <Badge>via {booking.source}</Badge>
        </div>
        {booking.title && <div className="font-semibold">{booking.title}</div>}
        <div>
          <div className="text-xs font-semibold uppercase text-muted">Players</div>
          {booking.players.length ? (
            <ul>
              {booking.players.map((p) => (
                <li key={p.id}>
                  <Link className="font-semibold text-court-700" to={`/admin/members/${p.id}`}>
                    {p.full_name}
                  </Link>{' '}
                  <span className="text-muted">NTRP {p.skill_level.toFixed(1)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-muted">No members yet</div>
          )}
          {booking.coach_name && <div className="mt-1">Coach: {booking.coach_name}</div>}
        </div>
        <PriceBreakdown base={booking.base_price} price={booking.price} lines={booking.price_breakdown} />
        <ErrorNote error={patch.error || cancel.error} />
        <div className="grid grid-cols-2 gap-2">
          <Button variant="secondary" onClick={() => patch.mutate({ paid: !booking.paid })}>
            Mark {booking.paid ? 'unpaid' : 'paid'}
          </Button>
          <Button variant="secondary" onClick={() => patch.mutate({ status: 'no_show' })}>
            No-show
          </Button>
          <Button variant="danger" className="col-span-2" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel booking
          </Button>
        </div>
      </div>
    </Modal>
  )
}
