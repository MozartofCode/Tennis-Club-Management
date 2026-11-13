import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { Button, Card, ErrorNote, Field, Input, PageHeader, Select, Textarea, Toggle } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth, type User } from '../../lib/auth'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const BLOCKS = [
  ['morning', 'Morning', '6-12'],
  ['afternoon', 'Afternoon', '12-5'],
  ['evening', 'Evening', '5-10'],
] as const

export function AvailabilityGrid({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const toggle = (key: string) => onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key])
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th />
            {DAYS.map((d) => (
              <th key={d} className="px-1 pb-1 font-semibold capitalize text-muted">
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BLOCKS.map(([key, label, hours]) => (
            <tr key={key}>
              <td className="pr-2 text-right">
                <div className="font-semibold">{label}</div>
                <div className="text-muted">{hours}</div>
              </td>
              {DAYS.map((d) => {
                const k = `${d}:${key}`
                return (
                  <td key={k} className="p-0.5">
                    <button
                      type="button"
                      aria-pressed={value.includes(k)}
                      aria-label={`${d} ${label}`}
                      onClick={() => toggle(k)}
                      className={clsx('h-9 w-10 rounded-lg border', value.includes(k) ? 'border-court-700 bg-court-600' : 'border-line bg-white hover:bg-court-50')}
                    />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Profile() {
  const { user, setUser } = useAuth()
  const [form, setForm] = useState({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
    skill_level: user?.skill_level ?? 3,
    availability: user?.availability ?? [],
    play_style: user?.play_style ?? '',
    goals: user?.goals ?? '',
    preferred_format: user?.preferred_format ?? 'singles',
    league_opt_in: user?.league_opt_in ?? false,
  })
  const save = useMutation({
    mutationFn: () => api<User>('/me', { method: 'PATCH', body: { ...form, phone: form.phone || null, play_style: form.play_style || null } }),
    onSuccess: setUser,
  })
  return (
    <div>
      <PageHeader title="Your tennis profile" sub="This is how we find you good matches and the right sessions." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-4">
          <Field label="Full name">
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Phone">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label="Level (NTRP)" hint="Coaches can adjust this. After a few matches, results fine-tune your matching.">
            <Select value={form.skill_level} onChange={(e) => setForm({ ...form, skill_level: Number(e.target.value) })}>
              {[1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7].map((l) => (
                <option key={l} value={l}>
                  {l.toFixed(1)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Play style">
            <Select value={form.play_style} onChange={(e) => setForm({ ...form, play_style: e.target.value })}>
              <option value="">Not sure</option>
              <option value="baseline">Baseliner</option>
              <option value="all-court">All-court</option>
              <option value="serve-volley">Serve & volley</option>
              <option value="social">Social / just for fun</option>
            </Select>
          </Field>
          <Field label="Goals">
            <Textarea rows={3} placeholder="e.g. Improve my backhand, play a league this summer" value={form.goals} onChange={(e) => setForm({ ...form, goals: e.target.value })} />
          </Field>
        </Card>
        <Card className="space-y-4">
          <Field label="When can you usually play?">
            <AvailabilityGrid value={form.availability} onChange={(availability) => setForm({ ...form, availability })} />
          </Field>
          <Field label="Format">
            <Select value={form.preferred_format} onChange={(e) => setForm({ ...form, preferred_format: e.target.value })}>
              <option value="singles">Singles</option>
              <option value="doubles">Doubles</option>
              <option value="either">Either</option>
            </Select>
          </Field>
          <Toggle checked={form.league_opt_in} onChange={(v) => setForm({ ...form, league_opt_in: v })} label="Pair me up automatically each week (club ladder)" />
          <ErrorNote error={save.error} />
          <Button className="w-full" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isSuccess ? 'Saved ✓' : 'Save profile'}
          </Button>
        </Card>
      </div>
    </div>
  )
}
