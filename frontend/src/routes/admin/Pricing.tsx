import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge, Button, Card, ErrorNote, Field, Input, PageHeader, Spinner, Stat } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dayLabel, hourLabel, money, pct } from '../../lib/format'
import { useClub } from '../../lib/queries'
import type { Club, PricingWeek, Simulation } from '../../lib/types'

const MODES: { value: Club['pricing_mode']; label: string; help: string }[] = [
  { value: 'off', label: 'Off', help: 'Everyone pays the standard price.' },
  { value: 'suggest', label: 'Suggest only', help: 'See what dynamic prices would be, but charge the standard price.' },
  { value: 'on', label: 'On', help: 'Members are charged the dynamic price, inside your limits.' },
]

function heat(price: number, base: number, min: number, max: number): string {
  if (price > base) {
    const t = Math.min(1, (price - base) / Math.max(1, max - base))
    return `rgba(200, 86, 42, ${0.12 + t * 0.7})`
  }
  if (price < base) {
    const t = Math.min(1, (base - price) / Math.max(1, base - min))
    return `rgba(47, 125, 79, ${0.12 + t * 0.7})`
  }
  return '#f4f3ee'
}

export function Pricing() {
  const club = useClub()
  const isOwner = useAuth((s) => s.user?.role === 'owner')
  const week = useQuery({ queryKey: ['pricing-week'], queryFn: () => api<PricingWeek>('/pricing/week') })
  const [hover, setHover] = useState<PricingWeek['slots'][number] | null>(null)
  if (!club.data || week.isLoading) return <Spinner />
  const c = club.data
  const w = week.data
  const slot = (d: string, h: number) => w?.slots.find((s) => s.date === d && s.hour === h)

  return (
    <div>
      <PageHeader title="Dynamic pricing" sub="Prices follow expected demand: busy hours earn more, quiet hours fill up with discounts. You set the limits." />
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <Card className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-bold">Next 7 days</h2>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="inline-block h-3 w-3 rounded" style={{ background: heat(c.min_price, c.base_price, c.min_price, c.max_price) }} /> discount
              <span className="inline-block h-3 w-3 rounded bg-[#f4f3ee]" /> standard
              <span className="inline-block h-3 w-3 rounded" style={{ background: heat(c.max_price, c.base_price, c.min_price, c.max_price) }} /> busy-hour
            </div>
          </div>
          {w && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-separate border-spacing-0.5 text-xs">
                <thead>
                  <tr>
                    <th />
                    {w.days.map((d) => (
                      <th key={d} className="pb-1 font-semibold">
                        {dayLabel(`${d}T00:00:00`).split(',')[0]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {w.hours.map((h) => (
                    <tr key={h}>
                      <td className="pr-2 text-right text-muted">{hourLabel(h)}</td>
                      {w.days.map((d) => {
                        const s = slot(d, h)
                        if (!s) return <td key={d} />
                        return (
                          <td key={d}>
                            <button
                              onMouseEnter={() => setHover(s)}
                              onFocus={() => setHover(s)}
                              className="h-8 w-full rounded-md font-semibold"
                              style={{ background: heat(s.suggested, w.base_price, c.min_price, c.max_price) }}
                            >
                              {Math.round(s.suggested)}
                            </button>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 min-h-[64px] rounded-xl bg-paper p-3 text-sm">
            {hover ? (
              <>
                <div className="font-semibold">
                  {dayLabel(`${hover.date}T00:00:00`)}, {hourLabel(hover.hour)}: {money(hover.suggested)}
                  {c.pricing_mode !== 'on' && <span className="font-normal text-muted"> (charging {money(hover.price)})</span>}
                </div>
                <div className="text-muted">
                  Forecast {pct(hover.forecast)} of courts booked · {pct(hover.booked)} already booked
                </div>
                {hover.reasons.map((r) => (
                  <div key={r.label}>
                    {r.label}: <b>{r.pct > 0 ? '+' : ''}{r.pct}%</b>
                  </div>
                ))}
              </>
            ) : (
              <span className="text-muted">Hover a cell to see why it's priced that way.</span>
            )}
          </div>
          {w && (
            <p className="mt-2 text-xs text-muted">
              Forecast model: {w.model.kind}, trained on {w.model.training_rows} court-hours
              {w.model.mae !== null && <> · typical error on the last two weeks ±{pct(w.model.mae)} of courts</>}.
            </p>
          )}
        </Card>
        <Limits club={c} canEdit={isOwner} />
      </div>
      <SimulationCard />
    </div>
  )
}

function Limits({ club, canEdit }: { club: Club; canEdit: boolean }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    pricing_mode: club.pricing_mode,
    base_price: club.base_price,
    min_price: club.min_price,
    max_price: club.max_price,
    max_surge_pct: club.max_surge_pct,
    max_discount_pct: club.max_discount_pct,
  })
  const save = useMutation({
    mutationFn: () => api<Club>('/club', { method: 'PATCH', body: form }),
    onSuccess: (data) => {
      qc.setQueryData(['club'], data)
      qc.invalidateQueries({ queryKey: ['pricing-week'] })
      qc.invalidateQueries({ queryKey: ['pricing-sim'] })
      qc.invalidateQueries({ queryKey: ['availability'] })
    },
  })
  const num = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: Number(e.target.value) })
  return (
    <Card className="space-y-4 self-start">
      <h2 className="font-bold">Your rules</h2>
      <div className="space-y-2">
        {MODES.map((m) => (
          <label key={m.value} className="flex cursor-pointer gap-3 rounded-xl border border-line p-3 has-[:checked]:border-court-700 has-[:checked]:bg-court-50">
            <input type="radio" name="mode" className="mt-1 accent-court-700" checked={form.pricing_mode === m.value} onChange={() => setForm({ ...form, pricing_mode: m.value })} disabled={!canEdit} />
            <span>
              <span className="block text-sm font-semibold">{m.label}</span>
              <span className="block text-xs text-muted">{m.help}</span>
            </span>
          </label>
        ))}
      </div>
      <Field label="Standard price per court-hour">
        <Input type="number" value={form.base_price} onChange={num('base_price')} disabled={!canEdit} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Never below">
          <Input type="number" value={form.min_price} onChange={num('min_price')} disabled={!canEdit} />
        </Field>
        <Field label="Never above">
          <Input type="number" value={form.max_price} onChange={num('max_price')} disabled={!canEdit} />
        </Field>
        <Field label="Max busy-hour +%">
          <Input type="number" value={form.max_surge_pct} onChange={num('max_surge_pct')} disabled={!canEdit} />
        </Field>
        <Field label="Max quiet-hour -%">
          <Input type="number" value={form.max_discount_pct} onChange={num('max_discount_pct')} disabled={!canEdit} />
        </Field>
      </div>
      <p className="text-xs text-muted">Member plan discounts are applied on top of the dynamic price.</p>
      <ErrorNote error={save.error} />
      {canEdit && (
        <Button className="w-full" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isSuccess ? 'Saved ✓' : 'Save rules'}
        </Button>
      )}
    </Card>
  )
}

function SimulationCard() {
  const [elasticity, setElasticity] = useState(0.6)
  const [unmet, setUnmet] = useState(0.15)
  const sim = useQuery({
    queryKey: ['pricing-sim', elasticity, unmet],
    queryFn: () => api<Simulation>(`/pricing/simulate?weeks=8&elasticity=${elasticity}&unmet=${unmet}`),
    placeholderData: (prev) => prev,
  })
  const s = sim.data
  const lift = s && s.flat_revenue ? (s.dynamic_revenue - s.flat_revenue) / s.flat_revenue : 0
  return (
    <Card className="mt-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-bold">What would the last 8 weeks have looked like?</h2>
          <p className="text-sm text-muted">A simulation on your real booking history, standard rates. The two assumptions are yours to change.</p>
        </div>
        <Badge tone="amber">Simulation</Badge>
      </div>
      <div className="mb-4 grid gap-4 sm:grid-cols-2">
        <Field label={`Price sensitivity: ${elasticity.toFixed(1)}`} hint="How much bookings drop when the price goes up 10%: 0.6 means about 6%.">
          <input type="range" min={0.1} max={1.5} step={0.1} value={elasticity} onChange={(e) => setElasticity(Number(e.target.value))} className="w-full accent-court-700" />
        </Field>
        <Field label={`Turned-away demand at full hours: ${Math.round(unmet * 100)}%`} hint="People who wanted a full hour but couldn't book.">
          <input type="range" min={0} max={0.5} step={0.05} value={unmet} onChange={(e) => setUnmet(Number(e.target.value))} className="w-full accent-court-700" />
        </Field>
      </div>
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Revenue, flat price" value={money(Math.round(s.flat_revenue))} />
            <Stat label="Revenue, dynamic" value={money(Math.round(s.dynamic_revenue))} sub={`${lift >= 0 ? '+' : ''}${pct(lift, 1)}`} tone={lift >= 0 ? 'good' : 'bad'} />
            <Stat label="Peak utilization" value={`${pct(s.peak_util_flat)} → ${pct(s.peak_util_dynamic)}`} sub="less overcrowding" />
            <Stat label="Off-peak utilization" value={`${pct(s.offpeak_util_flat)} → ${pct(s.offpeak_util_dynamic)}`} sub="quiet hours filling" tone="good" />
          </div>
          <div className="mt-4 h-64">
            <ResponsiveContainer>
              <BarChart data={s.by_hour.map((r) => ({ hour: hourLabel(r.hour), 'Flat price': Math.round(r.flat * 100), Dynamic: Math.round(r.dynamic * 100) }))}>
                <CartesianGrid vertical={false} stroke="#e3e2da" />
                <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                <YAxis unit="%" tick={{ fontSize: 11 }} width={40} />
                <Tooltip formatter={(v) => `${v}% of courts`} />
                <Legend />
                <Bar dataKey="Flat price" fill="#a9d3b6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Dynamic" fill="#1a5233" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  )
}
