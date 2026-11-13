import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Badge, Button, Card, Empty, ErrorNote, Input, PageHeader, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dayLabel, money, timeLabel } from '../../lib/format'
import type { Booking, MatchRow, MyMatches, Suggestion } from '../../lib/types'

export function Matches() {
  const user = useAuth((s) => s.user)
  const mine = useQuery({ queryKey: ['my-matches'], queryFn: () => api<MyMatches>('/matches/mine'), refetchInterval: 20_000 })
  const m = mine.data
  return (
    <div>
      <PageHeader title="Find a match" sub="Players at your level who are free when you are. Accept an invite and the court books itself, usually in a quieter, cheaper hour." />
      {m && m.incoming.length > 0 && <Incoming rows={m.incoming} />}
      {m && m.to_report.length > 0 && <ToReport rows={m.to_report} me={user!.id} />}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Suggestions />
        <div className="space-y-4">
          {m && (
            <Card>
              <h2 className="mb-2 font-bold">Your matches</h2>
              {m.upcoming.length === 0 && m.outgoing.length === 0 && <p className="text-sm text-muted">Nothing scheduled yet.</p>}
              <ul className="space-y-2 text-sm">
                {m.upcoming.map((x) => (
                  <li key={x.id}>
                    <b>{dayLabel(x.proposed_start)}</b> {timeLabel(x.proposed_start)} vs {x.requester_id === user!.id ? x.opponent_name : x.requester_name}
                    <span className="text-muted"> · {x.court_name}</span>
                  </li>
                ))}
                {m.outgoing.map((x) => (
                  <li key={x.id} className="text-muted">
                    Waiting on {x.opponent_name} · {dayLabel(x.proposed_start)} {timeLabel(x.proposed_start)}
                  </li>
                ))}
              </ul>
              {m.results.length > 0 && (
                <>
                  <h3 className="mb-1 mt-4 text-sm font-bold">Recent results</h3>
                  <ul className="space-y-1 text-sm">
                    {m.results.slice(0, 5).map((x) => {
                      const opp = x.requester_id === user!.id ? x.opponent_name : x.requester_name
                      return (
                        <li key={x.id} className="flex justify-between gap-2">
                          <span>vs {opp}</span>
                          <Badge tone={x.winner_id === user!.id ? 'green' : 'neutral'}>
                            {x.winner_id === user!.id ? 'Won' : 'Lost'} {x.score_text}
                          </Badge>
                        </li>
                      )
                    })}
                  </ul>
                </>
              )}
            </Card>
          )}
          <OpenClinics />
        </div>
      </div>
    </div>
  )
}

function Suggestions() {
  const qc = useQueryClient()
  const sugg = useQuery({ queryKey: ['match-suggestions'], queryFn: () => api<Suggestion[]>('/matches/suggestions') })
  const [sent, setSent] = useState<Record<number, string>>({})
  const invite = useMutation({
    mutationFn: (v: { s: Suggestion; slot: Suggestion['slots'][number] }) =>
      api('/matches', { body: { opponent_id: v.s.user_id, start_at: v.slot.start_at, court_id: v.slot.court_id } }),
    onSuccess: (_d, v) => {
      setSent({ ...sent, [v.s.user_id]: v.slot.start_at })
      qc.invalidateQueries({ queryKey: ['my-matches'] })
    },
  })
  if (sugg.isLoading) return <Spinner label="Finding players" />
  if (!sugg.data?.length) return <Empty title="No suggestions yet">Add when you can play in your profile so we can match you.</Empty>
  return (
    <div className="space-y-3">
      <ErrorNote error={invite.error} />
      {sugg.data.map((s) => (
        <Card key={s.user_id}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="font-display text-lg font-bold">{s.full_name}</div>
              <div className="text-sm text-muted">NTRP {s.skill_level.toFixed(1)}{s.play_style ? ` · ${s.play_style.replace('-', ' ')}` : ''}</div>
            </div>
            <Badge tone="ball">{Math.round(s.score * 100)}% match</Badge>
          </div>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {s.reasons.map((r) => (
              <li key={r} className="rounded-full bg-paper px-2 py-0.5 text-xs">
                {r}
              </li>
            ))}
          </ul>
          {sent[s.user_id] ? (
            <p className="mt-3 rounded-xl bg-court-50 p-2 text-sm">
              Invite sent for {dayLabel(sent[s.user_id])}, {timeLabel(sent[s.user_id])}. We'll book the court when they accept.
            </p>
          ) : (
            <div className="mt-3">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Invite for</div>
              <div className="flex flex-wrap gap-2">
                {s.slots.map((slot) => (
                  <Button key={slot.start_at} size="sm" variant="secondary" disabled={invite.isPending} onClick={() => invite.mutate({ s, slot })}>
                    {dayLabel(slot.start_at)}, {timeLabel(slot.start_at)} · {money(slot.per_person)} each
                    {slot.quiet && <span className="text-court-600">quiet</span>}
                  </Button>
                ))}
                {s.slots.length === 0 && <span className="text-sm text-muted">No shared free times this week.</span>}
              </div>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

function Incoming({ rows }: { rows: MatchRow[] }) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['my-matches'] })
    qc.invalidateQueries({ queryKey: ['my-bookings'] })
  }
  const accept = useMutation({ mutationFn: (id: number) => api(`/matches/${id}/accept`, { method: 'POST' }), onSuccess: refresh })
  const decline = useMutation({ mutationFn: (id: number) => api(`/matches/${id}/decline`, { method: 'POST' }), onSuccess: refresh })
  return (
    <div className="mb-4 space-y-2">
      {rows.map((m) => (
        <Card key={m.id} className="border-2 border-ball bg-ball-soft">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              {m.source === 'league' && <Badge tone="green">Weekly ladder</Badge>}
              <div className="mt-1 font-display text-lg font-bold">
                {m.source === 'league' ? `${m.requester_name} vs ${m.opponent_name}` : `${m.requester_name} wants a match`}
              </div>
              <div className="text-sm">
                {dayLabel(m.proposed_start)}, {timeLabel(m.proposed_start)}
                {m.court_name && ` · ${m.court_name}`}
              </div>
              {m.reasons[0] && <div className="text-xs text-muted">{m.reasons.join(' · ')}</div>}
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => decline.mutate(m.id)} disabled={decline.isPending}>
                Can't make it
              </Button>
              <Button onClick={() => accept.mutate(m.id)} disabled={accept.isPending}>
                Accept & book court
              </Button>
            </div>
          </div>
          <ErrorNote error={accept.error} />
        </Card>
      ))}
    </div>
  )
}

function ToReport({ rows, me }: { rows: MatchRow[]; me: number }) {
  const qc = useQueryClient()
  const [scores, setScores] = useState<Record<number, string>>({})
  const report = useMutation({
    mutationFn: (v: { id: number; winner: number }) => api(`/matches/${v.id}/result`, { body: { winner_id: v.winner, score_text: scores[v.id] ?? '' } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-matches'] }),
  })
  return (
    <Card className="mb-4">
      <h2 className="mb-2 font-bold">How did it go?</h2>
      <p className="mb-3 text-xs text-muted">Results keep your matches at the right level.</p>
      {rows.map((m) => {
        const oppId = m.requester_id === me ? m.opponent_id : m.requester_id
        const opp = m.requester_id === me ? m.opponent_name : m.requester_name
        return (
          <div key={m.id} className="flex flex-wrap items-center gap-2 border-t border-line py-2 text-sm first:border-0">
            <span className="flex-1">
              vs <b>{opp}</b> · {dayLabel(m.proposed_start)}
            </span>
            <Input className="w-28 py-1.5" placeholder="6-4 6-3" value={scores[m.id] ?? ''} onChange={(e) => setScores({ ...scores, [m.id]: e.target.value })} />
            <Button size="sm" onClick={() => report.mutate({ id: m.id, winner: me })}>
              I won
            </Button>
            <Button size="sm" variant="secondary" onClick={() => report.mutate({ id: m.id, winner: oppId })}>
              {opp.split(' ')[0]} won
            </Button>
          </div>
        )
      })}
    </Card>
  )
}

function OpenClinics() {
  const qc = useQueryClient()
  const user = useAuth((s) => s.user)
  const clinics = useQuery({ queryKey: ['open-clinics'], queryFn: () => api<Booking[]>('/clinics/open') })
  const join = useMutation({
    mutationFn: (id: number) => api(`/clinics/${id}/join`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['open-clinics'] })
      qc.invalidateQueries({ queryKey: ['my-bookings'] })
    },
  })
  if (!clinics.data?.length) return null
  return (
    <Card>
      <h2 className="mb-2 font-bold">Group clinics</h2>
      <ul className="space-y-3 text-sm">
        {clinics.data.slice(0, 5).map((c) => {
          const joined = c.players.some((p) => p.id === user?.id)
          return (
            <li key={c.id}>
              <div className="font-semibold">{c.title}</div>
              <div className="text-muted">
                {dayLabel(c.start_at)}, {timeLabel(c.start_at)} · {c.coach_name} · {c.capacity - c.players.length} spots left
              </div>
              {joined ? (
                <Badge tone="green">You're in</Badge>
              ) : (
                <Button size="sm" variant="secondary" className="mt-1" onClick={() => join.mutate(c.id)} disabled={join.isPending}>
                  Join ({money(Math.round(c.price / c.capacity))} each)
                </Button>
              )}
            </li>
          )
        })}
      </ul>
      <ErrorNote error={join.error} />
    </Card>
  )
}
