import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, PageHeader, Select, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dayLabel, timeLabel } from '../../lib/format'
import type { ClinicSuggestion, Coach, MatchRow } from '../../lib/types'

export function Matchmaking() {
  return (
    <div>
      <PageHeader title="Matchmaking & clinics" sub="Fill quiet hours with matches and group sessions. Members match themselves from their app; this is the club-wide view." />
      <div className="grid gap-4 lg:grid-cols-2">
        <League />
        <Clinics />
      </div>
    </div>
  )
}

function League() {
  const qc = useQueryClient()
  const league = useQuery({ queryKey: ['league'], queryFn: () => api<MatchRow[]>('/league') })
  const run = useMutation({
    mutationFn: () => api<MatchRow[]>('/league/run', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['league'] }),
  })
  const rows = league.data ?? []
  return (
    <Card className="self-start">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold">Weekly ladder</h2>
        <Button size="sm" variant="ball" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? 'Pairing…' : 'Pair players now'}
        </Button>
      </div>
      <p className="mb-3 text-sm text-muted">
        Members who opt in are paired every Sunday evening by match rating and shared free time, with a court proposed in a quiet hour. One tap to accept.
      </p>
      {run.data && <p className="mb-2 rounded-xl bg-court-50 p-2 text-sm">{run.data.length ? `Paired ${run.data.length} new matches.` : 'Everyone who opted in is already paired this week.'}</p>}
      {league.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty title="No ladder matches this week" />
      ) : (
        <ul className="divide-y divide-line text-sm">
          {rows.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <b>{m.requester_name}</b> vs <b>{m.opponent_name}</b>
                <span className="text-muted">
                  {' '}
                  · {dayLabel(m.proposed_start)} {timeLabel(m.proposed_start)}
                </span>
              </span>
              <Badge tone={m.status === 'accepted' ? 'green' : m.status === 'declined' ? 'clay' : 'neutral'}>{m.status === 'accepted' ? 'Court booked' : m.status}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function Clinics() {
  const sugg = useQuery({ queryKey: ['clinic-suggestions'], queryFn: () => api<ClinicSuggestion[]>('/clinics/suggestions') })
  return (
    <Card className="self-start">
      <h2 className="mb-2 font-bold">Clinic opportunities</h2>
      <p className="mb-3 text-sm text-muted">Quiet hours where enough similar-level members are free to fill a group session.</p>
      {sugg.isLoading ? (
        <Spinner />
      ) : !sugg.data?.length ? (
        <Empty title="No clear opportunities right now" />
      ) : (
        <div className="space-y-3">
          {sugg.data.map((s) => (
            <ClinicCard key={`${s.start_at}-${s.level}`} s={s} />
          ))}
        </div>
      )}
    </Card>
  )
}

function ClinicCard({ s }: { s: ClinicSuggestion }) {
  const qc = useQueryClient()
  const coaches = useQuery({ queryKey: ['coaches'], queryFn: () => api<Coach[]>('/club/coaches') })
  const [open, setOpen] = useState(false)
  const [coachId, setCoachId] = useState('')
  const [title, setTitle] = useState(`NTRP ${s.level} Drills`)
  const create = useMutation({
    mutationFn: () =>
      api('/clinics', {
        body: { court_id: s.court_id, start_at: s.start_at, coach_id: Number(coachId), title, invite_ids: s.members.map((m) => m.id) },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clinic-suggestions'] })
      qc.invalidateQueries({ queryKey: ['bookings'] })
    },
  })
  return (
    <div className="rounded-xl bg-paper p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <b>
          {dayLabel(s.start_at)}, {timeLabel(s.start_at)} · {s.court_name}
        </b>
        <Badge tone="blue">NTRP {s.level}</Badge>
      </div>
      <p className="mt-1 text-muted">{s.reason}</p>
      {create.isSuccess ? (
        <p className="mt-2 font-semibold text-court-700">Scheduled. {s.members.length} members invited.</p>
      ) : open ? (
        <div className="mt-2 space-y-2">
          <Field label="Clinic name">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Coach">
            <Select value={coachId} onChange={(e) => setCoachId(e.target.value)}>
              <option value="">Choose a coach</option>
              {(coaches.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.user.full_name}
                </option>
              ))}
            </Select>
          </Field>
          <p className="text-xs text-muted">Invites go to: {s.members.map((m) => m.name).join(', ')}</p>
          <ErrorNote error={create.error} />
          <Button size="sm" disabled={!coachId || create.isPending} onClick={() => create.mutate()}>
            Schedule & invite {s.members.length}
          </Button>
        </div>
      ) : (
        <Button size="sm" variant="secondary" className="mt-2" onClick={() => setOpen(true)}>
          Schedule clinic
        </Button>
      )}
    </div>
  )
}
