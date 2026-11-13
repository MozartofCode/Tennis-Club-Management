import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Empty, ErrorNote, PageHeader, Spinner, Stat, Tabs, Textarea } from '../../components/ui'
import { api } from '../../lib/api'
import { money, pct } from '../../lib/format'
import type { ChurnBoard, Offer, RiskRow } from '../../lib/types'

const BAND_TONE = { high: 'clay', medium: 'amber', low: 'green' } as const
const KIND_LABEL: Record<string, string> = {
  renewal_discount: 'Renewal discount',
  free_session: 'Free court hour',
  match_intro: 'Match introduction',
  lesson_upsell: 'Lesson upsell',
  clinic_invite: 'Clinic invite',
}

export function Retention() {
  const [tab, setTab] = useState<'risk' | 'drafts' | 'sent'>('risk')
  const board = useQuery({ queryKey: ['churn'], queryFn: () => api<ChurnBoard>('/churn') })
  const drafts = useQuery({ queryKey: ['offers', 'draft'], queryFn: () => api<Offer[]>('/offers?status=draft') })
  if (board.isLoading || !board.data) return <Spinner label="Scoring members" />
  const b = board.data
  const sent = (b.offers.sent ?? 0) + (b.offers.redeemed ?? 0)
  return (
    <div>
      <PageHeader
        title="Retention"
        sub="Members likely to leave in the next 6 weeks, why, and a ready-to-send offer for each. Nothing is sent without your approval."
        action={<Recompute />}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="High risk" value={b.counts.high ?? 0} sub={`${b.counts.medium ?? 0} medium`} tone="bad" />
        <Stat label="Monthly revenue at risk" value={money(b.revenue_at_risk)} sub="memberships of high-risk members" />
        <Stat label="Offers sent" value={sent} sub={`${b.offers.redeemed ?? 0} claimed`} />
        <Stat label="Drafts waiting" value={drafts.data?.length ?? 0} sub="review and send" />
      </div>
      <ModelCard model={b.model} />
      <div className="my-4">
        <Tabs
          value={tab}
          onChange={setTab}
          options={[
            { value: 'risk', label: 'At-risk members' },
            { value: 'drafts', label: `Offer drafts (${drafts.data?.length ?? 0})` },
            { value: 'sent', label: 'Sent' },
          ]}
        />
      </div>
      {tab === 'risk' && <RiskList rows={b.rows} onDrafted={() => setTab('drafts')} />}
      {tab === 'drafts' && <Drafts />}
      {tab === 'sent' && <SentOffers />}
    </div>
  )
}

function Recompute() {
  const qc = useQueryClient()
  const run = useMutation({
    mutationFn: () => api('/churn/recompute', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['churn'] }),
  })
  return (
    <Button variant="secondary" onClick={() => run.mutate()} disabled={run.isPending}>
      {run.isPending ? 'Scoring…' : 'Re-score now'}
    </Button>
  )
}

function ModelCard({ model }: { model: ChurnBoard['model'] }) {
  return (
    <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 bg-court-800 p-4 text-sm text-court-100">
      <span>
        <b className="text-white">How it works:</b> a {model.kind} model learns from your club's own history which habits come before members leave.
      </span>
      {model.auc !== undefined && (
        <span>
          Tested on the most recent period it never saw: ranks a leaver above a stayer <b className="text-ball">{pct(model.auc)}</b> of the time
          {model.recall_high !== undefined && (
            <>
              , catches <b className="text-ball">{pct(model.recall_high)}</b> of leavers in the high band
            </>
          )}
          .
        </span>
      )}
      <span className="text-xs text-court-200">Re-scored nightly. Reasons come straight from the model's weights.</span>
    </Card>
  )
}

function RiskList({ rows, onDrafted }: { rows: RiskRow[]; onDrafted: () => void }) {
  const qc = useQueryClient()
  const [band, setBand] = useState<'high' | 'medium' | 'all'>('high')
  const draft = useMutation({
    mutationFn: (ids: number[] | null) => api<{ created: number }>('/offers/generate', { body: { user_ids: ids, limit: ids ? ids.length : 15 } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['offers'] })
      qc.invalidateQueries({ queryKey: ['churn'] })
      onDrafted()
    },
  })
  const shown = rows.filter((r) => (band === 'all' ? r.band !== 'low' : r.band === band))
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Tabs
          value={band}
          onChange={setBand}
          options={[
            { value: 'high', label: 'High' },
            { value: 'medium', label: 'Medium' },
            { value: 'all', label: 'High + medium' },
          ]}
        />
        <Button variant="ball" disabled={draft.isPending} onClick={() => draft.mutate(null)}>
          {draft.isPending ? 'Drafting…' : 'Draft offers for the top members'}
        </Button>
      </div>
      <ErrorNote error={draft.error} />
      {shown.length === 0 ? (
        <Empty title="No members in this band" />
      ) : (
        <div className="space-y-2">
          {shown.map((r) => (
            <Card key={r.user_id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/admin/members/${r.user_id}`} className="font-semibold text-court-800 hover:underline">
                      {r.member_name}
                    </Link>
                    <Badge tone={BAND_TONE[r.band]}>{Math.round(r.score * 100)}% risk</Badge>
                    <span className="text-xs text-muted">
                      {r.visits_30} visits in 30 days · NTRP {r.skill_level.toFixed(1)}
                    </span>
                  </div>
                  <ul className="mt-2 space-y-1 text-sm">
                    {r.reasons.map((reason) => (
                      <li key={reason.key} className="flex items-center gap-2">
                        <span className="h-1.5 rounded-full bg-clay-500" style={{ width: `${Math.min(48, 8 + reason.weight * 14)}px` }} aria-hidden />
                        {reason.text}
                      </li>
                    ))}
                    {r.reasons.length === 0 && <li className="text-muted">No single standout reason</li>}
                  </ul>
                </div>
                <div className="flex items-center gap-2">
                  <div className="hidden h-2 w-24 overflow-hidden rounded-full bg-stone-100 sm:block">
                    <div className={clsx('h-full', r.band === 'high' ? 'bg-clay-500' : r.band === 'medium' ? 'bg-amber-400' : 'bg-court-500')} style={{ width: `${r.score * 100}%` }} />
                  </div>
                  {r.offer_status ? (
                    <Badge tone={r.offer_status === 'redeemed' ? 'green' : 'neutral'}>Offer {r.offer_status}</Badge>
                  ) : (
                    <Button size="sm" variant="secondary" disabled={draft.isPending} onClick={() => draft.mutate([r.user_id])}>
                      Draft offer
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function Drafts() {
  const qc = useQueryClient()
  const drafts = useQuery({ queryKey: ['offers', 'draft'], queryFn: () => api<Offer[]>('/offers?status=draft') })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['offers'] })
    qc.invalidateQueries({ queryKey: ['churn'] })
  }
  if (drafts.isLoading) return <Spinner />
  if (!drafts.data?.length) return <Empty title="No drafts">Draft offers from the at-risk list. Upsell ideas for engaged members appear here too.</Empty>
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {drafts.data.map((o) => (
        <DraftCard key={o.id} offer={o} onDone={refresh} />
      ))}
    </div>
  )
}

function DraftCard({ offer, onDone }: { offer: Offer; onDone: () => void }) {
  const [message, setMessage] = useState(offer.message)
  const send = useMutation({
    mutationFn: async () => {
      if (message !== offer.message) await api(`/offers/${offer.id}`, { method: 'PATCH', body: { message } })
      return api(`/offers/${offer.id}/send`, { method: 'POST' })
    },
    onSuccess: onDone,
  })
  const dismiss = useMutation({ mutationFn: () => api(`/offers/${offer.id}/dismiss`, { method: 'POST' }), onSuccess: onDone })
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">To {offer.member_name}</div>
          <div className="font-bold">{offer.title}</div>
        </div>
        <div className="flex gap-1">
          <Badge tone={offer.source === 'upsell' ? 'blue' : 'clay'}>{offer.source === 'upsell' ? 'Upsell' : 'Retention'}</Badge>
          <Badge>{KIND_LABEL[offer.kind] ?? offer.kind}</Badge>
        </div>
      </div>
      {offer.reason && <p className="text-xs text-muted">Because: {offer.reason}</p>}
      <Textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted">{offer.written_by === 'claude' ? 'Written by Claude, edit freely' : 'From template'}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => dismiss.mutate()} disabled={dismiss.isPending}>
            Dismiss
          </Button>
          <Button size="sm" onClick={() => send.mutate()} disabled={send.isPending}>
            Approve & send
          </Button>
        </div>
      </div>
      <ErrorNote error={send.error} />
    </Card>
  )
}

function SentOffers() {
  const sent = useQuery({ queryKey: ['offers', 'all'], queryFn: () => api<Offer[]>('/offers') })
  const rows = (sent.data ?? []).filter((o) => o.status === 'sent' || o.status === 'redeemed')
  if (!rows.length) return <Empty title="Nothing sent yet" />
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((o) => (
            <tr key={o.id} className="border-t border-line first:border-0">
              <td className="p-3 font-semibold">{o.member_name}</td>
              <td className="p-3">{o.title}</td>
              <td className="p-3 text-muted">{KIND_LABEL[o.kind] ?? o.kind}</td>
              <td className="p-3 text-right">
                <Badge tone={o.status === 'redeemed' ? 'green' : 'neutral'}>{o.status === 'redeemed' ? 'Claimed' : 'Sent'}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
