import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Select, Spinner, Toggle } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { hourLabel, money } from '../../lib/format'
import { useClub } from '../../lib/queries'
import type { Club, Coach, Court, Plan } from '../../lib/types'

const STEPS = ['Club & hours', 'Courts', 'Prices & plans', 'Coaches & staff', 'Members'] as const
const TIMEZONES = ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London', 'Europe/Istanbul', 'Europe/Paris', 'Australia/Sydney']

export function Setup() {
  const [step, setStep] = useState(0)
  const club = useClub()
  const isOwner = useAuth((s) => s.user?.role === 'owner')
  if (club.isLoading || !club.data) return <Spinner />
  return (
    <div>
      <PageHeader
        title="Club setup"
        sub={club.data.setup_complete ? 'Your club is live. Change anything here at any time.' : 'Five short steps. You can come back and change anything later.'}
      />
      {!isOwner && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Only the owner can change club settings. You can view them here.</p>}
      <ol className="mb-6 flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <li key={s}>
            <button
              onClick={() => setStep(i)}
              className={clsx(
                'flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold',
                i === step ? 'border-court-800 bg-court-800 text-white' : 'border-line bg-white text-muted hover:text-ink',
              )}
            >
              <span className={clsx('flex h-5 w-5 items-center justify-center rounded-full text-xs', i === step ? 'bg-ball text-court-900' : 'bg-stone-100')}>{i + 1}</span>
              {s}
            </button>
          </li>
        ))}
      </ol>
      {step === 0 && <ClubStep club={club.data} onNext={() => setStep(1)} />}
      {step === 1 && <CourtsStep onNext={() => setStep(2)} />}
      {step === 2 && <PricesStep club={club.data} onNext={() => setStep(3)} />}
      {step === 3 && <PeopleStep onNext={() => setStep(4)} />}
      {step === 4 && <MembersStep club={club.data} />}
    </div>
  )
}

function useSaveClub() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Club>) => api<Club>('/club', { method: 'PATCH', body }),
    onSuccess: (club) => qc.setQueryData(['club'], club),
  })
}

function ClubStep({ club, onNext }: { club: Club; onNext: () => void }) {
  const save = useSaveClub()
  const [form, setForm] = useState({
    name: club.name,
    city: club.city ?? '',
    timezone: club.timezone,
    open_hour: club.open_hour,
    close_hour: club.close_hour,
    weekday: club.peak_hours.weekday ?? [],
    weekend: club.peak_hours.weekend ?? [],
  })
  const hours = Array.from({ length: 24 }, (_, i) => i)
  const togglePeak = (kind: 'weekday' | 'weekend', h: number) =>
    setForm({ ...form, [kind]: form[kind].includes(h) ? form[kind].filter((x) => x !== h) : [...form[kind], h].sort((a, b) => a - b) })

  return (
    <Card className="max-w-3xl space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Club name">
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="City" hint="Used for weather-aware pricing on outdoor courts.">
          <Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
        </Field>
        <Field label="Time zone">
          <Select value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })}>
            {[...new Set([form.timezone, ...TIMEZONES])].map((tz) => (
              <option key={tz}>{tz}</option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Opens">
            <Select value={form.open_hour} onChange={(e) => setForm({ ...form, open_hour: Number(e.target.value) })}>
              {hours.map((h) => (
                <option key={h} value={h}>{hourLabel(h)}</option>
              ))}
            </Select>
          </Field>
          <Field label="Closes">
            <Select value={form.close_hour} onChange={(e) => setForm({ ...form, close_hour: Number(e.target.value) })}>
              {hours.slice(1).concat(24).map((h) => (
                <option key={h} value={h}>{h === 24 ? 'Midnight' : hourLabel(h)}</option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
      {(['weekday', 'weekend'] as const).map((kind) => (
        <div key={kind}>
          <div className="mb-2 text-sm font-semibold">{kind === 'weekday' ? 'Weekday' : 'Weekend'} peak hours</div>
          <div className="flex flex-wrap gap-1.5">
            {hours.filter((h) => h >= form.open_hour && h < form.close_hour).map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => togglePeak(kind, h)}
                className={clsx('rounded-lg border px-2 py-1 text-xs font-semibold', form[kind].includes(h) ? 'border-court-700 bg-court-700 text-white' : 'border-line bg-white')}
              >
                {hourLabel(h)}
              </button>
            ))}
          </div>
        </div>
      ))}
      <ErrorNote error={save.error} />
      <Button
        disabled={save.isPending}
        onClick={() =>
          save.mutate(
            { name: form.name, city: form.city || null, timezone: form.timezone, open_hour: form.open_hour, close_hour: form.close_hour, peak_hours: { weekday: form.weekday, weekend: form.weekend } },
            { onSuccess: onNext },
          )
        }
      >
        Save and continue
      </Button>
    </Card>
  )
}

function CourtsStep({ onNext }: { onNext: () => void }) {
  const qc = useQueryClient()
  const courts = useQuery({ queryKey: ['courts'], queryFn: () => api<Court[]>('/club/courts') })
  const [form, setForm] = useState({ name: '', surface: 'hard', indoor: false, has_lights: true })
  const add = useMutation({
    mutationFn: () => api<Court>('/club/courts', { body: { ...form, name: form.name.trim() || `Court ${(courts.data?.length ?? 0) + 1}` } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['courts'] })
      setForm({ ...form, name: '' })
    },
  })
  const update = useMutation({
    mutationFn: (c: Court) => api<Court>(`/club/courts/${c.id}`, { method: 'PATCH', body: c }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['courts'] }),
  })
  const list = courts.data ?? []
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <h2 className="mb-3 font-bold">Your courts ({list.filter((c) => c.is_active).length} active)</h2>
        {list.length === 0 && <p className="text-sm text-muted">No courts yet. Add your first one.</p>}
        <ul className="divide-y divide-line">
          {list.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <div className={clsx('font-semibold', !c.is_active && 'text-muted line-through')}>{c.name}</div>
                <div className="mt-1 flex gap-1.5">
                  <Badge>{c.surface}</Badge>
                  <Badge tone={c.indoor ? 'blue' : 'ball'}>{c.indoor ? 'Indoor' : 'Outdoor'}</Badge>
                  {c.has_lights && <Badge>Lights</Badge>}
                </div>
              </div>
              <Toggle checked={c.is_active} onChange={(v) => update.mutate({ ...c, is_active: v })} label={c.is_active ? 'Open' : 'Closed'} />
            </li>
          ))}
        </ul>
      </Card>
      <Card className="space-y-3 self-start">
        <h2 className="font-bold">Add a court</h2>
        <Field label="Name">
          <Input placeholder={`Court ${list.length + 1}`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Surface">
          <Select value={form.surface} onChange={(e) => setForm({ ...form, surface: e.target.value })}>
            {['hard', 'clay', 'grass', 'carpet'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <div className="flex flex-col gap-2">
          <Toggle checked={form.indoor} onChange={(v) => setForm({ ...form, indoor: v })} label="Indoor" />
          <Toggle checked={form.has_lights} onChange={(v) => setForm({ ...form, has_lights: v })} label="Has lights" />
        </div>
        <ErrorNote error={add.error} />
        <Button className="w-full" disabled={add.isPending} onClick={() => add.mutate()}>
          Add court
        </Button>
        <Button variant="secondary" className="w-full" disabled={list.length === 0} onClick={onNext}>
          Continue
        </Button>
      </Card>
    </div>
  )
}

function PricesStep({ club, onNext }: { club: Club; onNext: () => void }) {
  const qc = useQueryClient()
  const save = useSaveClub()
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api<Plan[]>('/club/plans') })
  const [base, setBase] = useState(club.base_price)
  const [plan, setPlan] = useState({ name: '', monthly_price: 90, court_discount_pct: 15, priority: 1, description: '' })
  const add = useMutation({
    mutationFn: () => api<Plan>('/club/plans', { body: plan }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      setPlan({ ...plan, name: '' })
    },
  })
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-4">
        <h2 className="font-bold">Standard court price</h2>
        <Field label={`Price per court-hour (${club.currency})`} hint="Dynamic pricing adjusts around this number, within limits you control on the Pricing page.">
          <Input type="number" min={1} value={base} onChange={(e) => setBase(Number(e.target.value))} />
        </Field>
        <ErrorNote error={save.error} />
        <Button variant="secondary" onClick={() => save.mutate({ base_price: base })} disabled={save.isPending}>
          {save.isSuccess ? 'Saved' : 'Save price'}
        </Button>

        <h2 className="pt-4 font-bold">Membership plans</h2>
        <ul className="divide-y divide-line">
          {(plans.data ?? []).map((p) => (
            <li key={p.id} className="flex justify-between py-2 text-sm">
              <span className="font-semibold">{p.name}</span>
              <span className="text-muted">
                {money(p.monthly_price, club.currency)}/mo · {p.court_discount_pct}% off courts · priority {p.priority}
              </span>
            </li>
          ))}
        </ul>
        {plans.data?.length === 0 && <p className="text-sm text-muted">No plans yet.</p>}
      </Card>
      <Card className="space-y-3 self-start">
        <h2 className="font-bold">Add a plan</h2>
        <Field label="Plan name">
          <Input placeholder="e.g. Gold" value={plan.name} onChange={(e) => setPlan({ ...plan, name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Monthly price">
            <Input type="number" min={0} value={plan.monthly_price} onChange={(e) => setPlan({ ...plan, monthly_price: Number(e.target.value) })} />
          </Field>
          <Field label="Court discount %">
            <Input type="number" min={0} max={100} value={plan.court_discount_pct} onChange={(e) => setPlan({ ...plan, court_discount_pct: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Waitlist priority" hint="Higher tiers get first pick when a slot frees up.">
          <Select value={plan.priority} onChange={(e) => setPlan({ ...plan, priority: Number(e.target.value) })}>
            <option value={0}>Standard</option>
            <option value={1}>Priority</option>
            <option value={2}>High priority</option>
            <option value={3}>Top priority</option>
          </Select>
        </Field>
        <ErrorNote error={add.error} />
        <Button className="w-full" disabled={!plan.name || add.isPending} onClick={() => add.mutate()}>
          Add plan
        </Button>
        <Button variant="secondary" className="w-full" onClick={onNext}>
          Continue
        </Button>
      </Card>
    </div>
  )
}

function PeopleStep({ onNext }: { onNext: () => void }) {
  const qc = useQueryClient()
  const coaches = useQuery({ queryKey: ['coaches'], queryFn: () => api<Coach[]>('/club/coaches') })
  const [kind, setKind] = useState<'coach' | 'staff'>('coach')
  const [form, setForm] = useState({ full_name: '', email: '', specialties: '', hourly_rate: 70 })
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null)
  const add = useMutation({
    mutationFn: () =>
      api<{ user: { email: string }; temporary_password: string }>(kind === 'coach' ? '/club/coaches' : '/club/staff', {
        body: kind === 'coach' ? form : { full_name: form.full_name, email: form.email },
      }),
    onSuccess: (r) => {
      setCreated({ email: r.user.email, password: r.temporary_password })
      qc.invalidateQueries({ queryKey: ['coaches'] })
      setForm({ full_name: '', email: '', specialties: '', hourly_rate: 70 })
    },
  })
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <h2 className="mb-3 font-bold">Coaches</h2>
        <ul className="divide-y divide-line">
          {(coaches.data ?? []).map((c) => (
            <li key={c.id} className="py-2 text-sm">
              <div className="font-semibold">{c.user.full_name}</div>
              <div className="text-muted">
                {c.specialties || 'General coaching'} · {money(c.hourly_rate)}/hr
              </div>
            </li>
          ))}
        </ul>
        {coaches.data?.length === 0 && <p className="text-sm text-muted">No coaches yet.</p>}
      </Card>
      <Card className="space-y-3 self-start">
        <div className="flex gap-2">
          <Button size="sm" variant={kind === 'coach' ? 'primary' : 'secondary'} onClick={() => setKind('coach')}>
            Add coach
          </Button>
          <Button size="sm" variant={kind === 'staff' ? 'primary' : 'secondary'} onClick={() => setKind('staff')}>
            Add front-desk staff
          </Button>
        </div>
        <Field label="Full name">
          <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Email" hint="They sign in with this email and the temporary password shown after saving.">
          <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        {kind === 'coach' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Specialties">
              <Input placeholder="Juniors, serve" value={form.specialties} onChange={(e) => setForm({ ...form, specialties: e.target.value })} />
            </Field>
            <Field label="Hourly rate">
              <Input type="number" value={form.hourly_rate} onChange={(e) => setForm({ ...form, hourly_rate: Number(e.target.value) })} />
            </Field>
          </div>
        )}
        <ErrorNote error={add.error} />
        {created && (
          <div className="rounded-xl bg-ball-soft p-3 text-sm">
            Account created for <b>{created.email}</b>. Temporary password: <code className="rounded bg-white px-1.5 py-0.5 font-bold">{created.password}</code>
            <div className="text-xs text-muted">Share it with them privately; it's only shown once.</div>
          </div>
        )}
        <Button className="w-full" disabled={!form.full_name || !form.email || add.isPending} onClick={() => add.mutate()}>
          Create account
        </Button>
        <Button variant="secondary" className="w-full" onClick={onNext}>
          Continue
        </Button>
      </Card>
    </div>
  )
}

function MembersStep({ club }: { club: Club }) {
  const save = useSaveClub()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const upload = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('file', file as File)
      return api<{ created: number; skipped: string[] }>('/members/import', { body: fd })
    },
  })
  const joinLink = `${window.location.origin}/join?club=${club.id}`
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3">
        <h2 className="font-bold">Import your member list</h2>
        <p className="text-sm text-muted">
          Export from your spreadsheet as CSV. We look for columns named <b>name</b>, <b>email</b>, <b>phone</b>, <b>level</b> and <b>plan</b> (plan names must match the plans you created).
        </p>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
        <ErrorNote error={upload.error} />
        {upload.data && (
          <div className="rounded-xl bg-court-50 p-3 text-sm">
            Imported <b>{upload.data.created}</b> members.
            {upload.data.skipped.length > 0 && (
              <ul className="mt-1 list-disc pl-5 text-muted">
                {upload.data.skipped.slice(0, 5).map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <Button disabled={!file || upload.isPending} onClick={() => upload.mutate()}>
          Import CSV
        </Button>
      </Card>
      <Card className="space-y-3 self-start">
        <h2 className="font-bold">Or invite members to sign up</h2>
        <p className="text-sm text-muted">Share this link. Members create a profile, pick their level, and get a check-in QR code.</p>
        <code className="block break-all rounded-xl bg-paper p-3 text-xs">{joinLink}</code>
        <Button variant="secondary" onClick={() => navigator.clipboard?.writeText(joinLink)}>
          Copy link
        </Button>
        <div className="border-t border-line pt-4">
          <Button className="w-full" variant="ball" onClick={() => save.mutate({ setup_complete: true }, { onSuccess: () => navigate('/admin') })}>
            {club.setup_complete ? 'Done' : 'Finish setup'}
          </Button>
        </div>
      </Card>
    </div>
  )
}
