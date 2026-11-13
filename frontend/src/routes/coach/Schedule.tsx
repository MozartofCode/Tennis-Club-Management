import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Card, Empty, PageHeader, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dayLabel, relativeDays, timeLabel } from '../../lib/format'
import type { Booking } from '../../lib/types'

interface Student {
  id: number
  full_name: string
  skill_level: number
  sessions: number
  last_session: string | null
}

export function CoachSchedule() {
  const qc = useQueryClient()
  const schedule = useQuery({ queryKey: ['coach-schedule'], queryFn: () => api<Booking[]>('/coach/schedule') })
  const students = useQuery({ queryKey: ['coach-students'], queryFn: () => api<Student[]>('/coach/students') })
  const setLevel = useMutation({
    mutationFn: ({ id, level }: { id: number; level: number }) => api(`/coach/students/${id}/level`, { method: 'PATCH', body: { skill_level: level } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['coach-students'] }),
  })
  const byDay = new Map<string, Booking[]>()
  for (const b of schedule.data ?? []) byDay.set(b.start_at.slice(0, 10), [...(byDay.get(b.start_at.slice(0, 10)) ?? []), b])

  return (
    <div>
      <PageHeader title="My schedule" sub="Lessons and clinics for the next two weeks." />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-3">
          {schedule.isLoading && <Spinner />}
          {schedule.data?.length === 0 && <Empty title="No sessions booked" />}
          {[...byDay.entries()].map(([day, list]) => (
            <Card key={day}>
              <h2 className="mb-2 font-bold">{dayLabel(`${day}T00:00:00`)}</h2>
              <ul className="divide-y divide-line text-sm">
                {list.map((b) => (
                  <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>
                      <b>{timeLabel(b.start_at)}</b> · {b.court_name} · {b.title || b.players.map((p) => `${p.full_name} (${p.skill_level.toFixed(1)})`).join(', ') || 'Open'}
                    </span>
                    <span className="flex gap-1">
                      <Badge className="capitalize">{b.type}</Badge>
                      {b.type === 'clinic' && (
                        <Badge tone="blue">
                          {b.players.length}/{b.capacity}
                        </Badge>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
        <Card className="self-start">
          <h2 className="mb-2 font-bold">My students</h2>
          <p className="mb-3 text-xs text-muted">Adjust a level if a student rated themselves too high or low; it improves their matches.</p>
          <ul className="divide-y divide-line text-sm">
            {(students.data ?? []).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                <div>
                  <div className="font-semibold">{s.full_name}</div>
                  <div className="text-xs text-muted">
                    {s.sessions} sessions{s.last_session ? ` · last ${relativeDays(s.last_session)}` : ''}
                  </div>
                </div>
                <Select className="w-20 py-1" value={s.skill_level} onChange={(e) => setLevel.mutate({ id: s.id, level: Number(e.target.value) })}>
                  {[1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7].map((l) => (
                    <option key={l} value={l}>
                      {l.toFixed(1)}
                    </option>
                  ))}
                </Select>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
