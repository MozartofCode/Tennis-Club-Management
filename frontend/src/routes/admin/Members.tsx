import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { dayLabel, money, relativeDays, timeLabel } from '../../lib/format'
import type { MemberDetail as Detail, MemberRow, Plan } from '../../lib/types'

const STATUS_TONE = { active: 'green', expiring: 'amber', expired: 'clay', none: 'neutral' } as const
const BAND_TONE = { low: 'green', medium: 'amber', high: 'clay' } as const

export function Members() {
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [adding, setAdding] = useState(false)
  const members = useQuery({ queryKey: ['members'], queryFn: () => api<MemberRow[]>('/members') })
  const rows = (members.data ?? []).filter((m) => {
    const hit = !q || `${m.full_name} ${m.email}`.toLowerCase().includes(q.toLowerCase())
    const f = filter === 'all' || m.membership_status === filter || (filter === 'at-risk' && m.churn_band === 'high')
    return hit && f
  })
  return (
    <div>
      <PageHeader title="Members" sub={`${members.data?.length ?? 0} members`} action={<Button onClick={() => setAdding(true)}>Add member</Button>} />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input className="max-w-xs" placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select className="max-w-[200px]" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All members</option>
          <option value="active">Active</option>
          <option value="expiring">Expiring soon</option>
          <option value="expired">Expired</option>
          <option value="none">No membership</option>
          <option value="at-risk">High churn risk</option>
        </Select>
      </div>
      {members.isLoading ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <Empty title="No members found">Import a CSV in Club setup, or add members one by one.</Empty>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="p-3">Member</th>
                <th className="p-3">Level</th>
                <th className="p-3">Membership</th>
                <th className="p-3">Last visit</th>
                <th className="p-3">Visits (30d)</th>
                <th className="p-3">Churn risk</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-t border-line hover:bg-court-50/50">
                  <td className="p-3">
                    <Link to={`/admin/members/${m.id}`} className="font-semibold text-court-800 hover:underline">
                      {m.full_name}
                    </Link>
                    <div className="text-xs text-muted">{m.email}</div>
                  </td>
                  <td className="p-3">{m.skill_level.toFixed(1)}</td>
                  <td className="p-3">
                    <Badge tone={STATUS_TONE[m.membership_status]}>{m.plan ?? 'None'}</Badge>
                    {m.membership_status === 'expiring' && <div className="text-xs text-amber-700">ends {m.membership_end}</div>}
                    {m.membership_status === 'expired' && <div className="text-xs text-clay-600">expired</div>}
                  </td>
                  <td className="p-3 text-muted">{m.last_visit ? relativeDays(m.last_visit) : 'Never'}</td>
                  <td className="p-3">{m.visits_30d}</td>
                  <td className="p-3">{m.churn_band ? <Badge tone={BAND_TONE[m.churn_band]}>{Math.round((m.churn_score ?? 0) * 100)}%</Badge> : <span className="text-muted">-</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding && <AddMember onClose={() => setAdding(false)} />}
    </div>
  )
}

function AddMember({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/club/plans') })
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', skill_level: 3, plan_id: '' })
  const add = useMutation({
    mutationFn: () => api('/members', { body: { ...form, phone: form.phone || null, plan_id: form.plan_id ? Number(form.plan_id) : null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] })
      onClose()
    },
  })
  return (
    <Modal open onClose={onClose} title="Add member">
      <div className="space-y-3">
        <Field label="Full name">
          <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Email">
          <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Phone">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label="Level (NTRP)">
            <Input type="number" step={0.5} min={1} max={7} value={form.skill_level} onChange={(e) => setForm({ ...form, skill_level: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Membership plan">
          <Select value={form.plan_id} onChange={(e) => setForm({ ...form, plan_id: e.target.value })}>
            <option value="">No plan (pay as you go)</option>
            {(plans.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({money(p.monthly_price)}/mo)
              </option>
            ))}
          </Select>
        </Field>
        <ErrorNote error={add.error} />
        <Button className="w-full" disabled={!form.full_name || !form.email || add.isPending} onClick={() => add.mutate()}>
          Add member
        </Button>
      </div>
    </Modal>
  )
}

export function MemberDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['member', id], queryFn: () => api<Detail>(`/members/${id}`) })
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/club/plans') })
  const [planId, setPlanId] = useState('')
  const renew = useMutation({
    mutationFn: () => api(`/members/${id}/membership`, { body: { plan_id: Number(planId), months: 1 } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['member', id] })
      qc.invalidateQueries({ queryKey: ['members'] })
    },
  })
  const checkIn = useMutation({
    mutationFn: () => api('/checkin/manual', { body: { user_id: Number(id) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['member', id] }),
  })
  if (detail.isLoading || !detail.data) return <Spinner />
  const { user, membership, stats, upcoming, recent, check_ins } = detail.data
  return (
    <div>
      <Link to="/admin/members" className="text-sm font-semibold text-court-700">
        ← Members
      </Link>
      <PageHeader
        title={user.full_name}
        sub={`${user.email}${user.phone ? ` · ${user.phone}` : ''} · NTRP ${user.skill_level.toFixed(1)} · member since ${dayLabel(user.created_at)}`}
        action={
          <Button variant="secondary" onClick={() => checkIn.mutate()} disabled={checkIn.isPending}>
            {checkIn.isSuccess ? 'Checked in ✓' : 'Check in manually'}
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Visits (30 days)" value={stats.visits_30d} sub={`${stats.total_visits} all time`} />
        <Stat label="Bookings" value={stats.bookings_total} sub={`${stats.cancellations} cancelled · ${stats.no_shows} no-shows`} />
        <Stat label="Lessons & clinics" value={stats.lessons} />
        <Stat label="Spend (90 days)" value={money(stats.spend_90d)} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="space-y-3">
          <h2 className="font-bold">Membership</h2>
          {membership ? (
            <div className="text-sm">
              <div className="font-semibold">{membership.plan.name}</div>
              <div className="text-muted">
                Until {membership.end_date} · auto-renew {membership.auto_renew ? 'on' : 'off'}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">No active membership.</p>
          )}
          <Field label={membership ? 'Renew or change plan' : 'Start a plan'}>
            <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
              <option value="">Choose a plan</option>
              {(plans.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({money(p.monthly_price)}/mo)
                </option>
              ))}
            </Select>
          </Field>
          <ErrorNote error={renew.error} />
          <Button size="sm" disabled={!planId || renew.isPending} onClick={() => renew.mutate()}>
            Start 1 month
          </Button>
          {user.goals && (
            <div className="border-t border-line pt-3 text-sm">
              <div className="text-xs font-semibold uppercase text-muted">Goals</div>
              {user.goals}
            </div>
          )}
        </Card>
        <Card>
          <h2 className="mb-2 font-bold">Upcoming</h2>
          {upcoming.length === 0 && <p className="text-sm text-muted">Nothing booked.</p>}
          <ul className="space-y-2 text-sm">
            {upcoming.map((b) => (
              <li key={b.id}>
                <b>{dayLabel(b.start_at)}</b> {timeLabel(b.start_at)} · {b.court_name} <span className="capitalize text-muted">· {b.type}</span>
              </li>
            ))}
          </ul>
          <h2 className="mb-2 mt-4 font-bold">Recent</h2>
          <ul className="space-y-1 text-sm">
            {recent.slice(0, 8).map((b) => (
              <li key={b.id} className="flex justify-between gap-2">
                <span>
                  {dayLabel(b.start_at)} · <span className="capitalize">{b.type}</span>
                </span>
                {b.status !== 'completed' && b.status !== 'booked' && <Badge tone="clay">{b.status.replace('_', '-')}</Badge>}
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="mb-2 font-bold">Check-ins</h2>
          {check_ins.length === 0 && <p className="text-sm text-muted">No visits recorded.</p>}
          <ul className="space-y-1 text-sm">
            {check_ins.slice(0, 12).map((c) => (
              <li key={c.id} className="flex justify-between">
                <span>
                  {dayLabel(c.created_at)} {timeLabel(c.created_at)}
                </span>
                <span className="text-muted">{c.court_name ?? c.method}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
