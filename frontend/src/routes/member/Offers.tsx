import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, Empty, PageHeader, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import type { Offer } from '../../lib/types'

export function MemberOffers() {
  const qc = useQueryClient()
  const offers = useQuery({ queryKey: ['my-offers'], queryFn: () => api<Offer[]>('/me/offers') })
  const redeem = useMutation({
    mutationFn: (id: number) => api(`/me/offers/${id}/redeem`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-offers'] }),
  })
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Offers for you" sub="Perks from your club." />
      {offers.isLoading ? (
        <Spinner />
      ) : !offers.data?.length ? (
        <Empty title="No offers right now">We'll let you know when there's something for you.</Empty>
      ) : (
        <div className="space-y-3">
          {offers.data.map((o) => (
            <Card key={o.id} className={o.status === 'sent' ? 'border-ball' : ''}>
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-display text-lg font-bold">{o.title}</h2>
                {o.status === 'redeemed' && <Badge tone="green">Claimed</Badge>}
              </div>
              <p className="mt-2 text-sm">{o.message}</p>
              {o.status === 'sent' && (
                <Button className="mt-4" variant="ball" onClick={() => redeem.mutate(o.id)} disabled={redeem.isPending}>
                  Claim offer
                </Button>
              )}
              {o.status === 'redeemed' && <p className="mt-3 text-xs text-muted">Show this at the front desk; they'll apply it for you.</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
