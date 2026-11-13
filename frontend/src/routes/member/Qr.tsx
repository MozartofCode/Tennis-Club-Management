import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { Button, Card, PageHeader, Spinner } from '../../components/ui'
import { api } from '../../lib/api'

interface Qr {
  token: string
  name: string
  club: string
}

export function MyQr() {
  const qc = useQueryClient()
  const qr = useQuery({ queryKey: ['qr'], queryFn: () => api<Qr>('/me/qr') })
  const rotate = useMutation({
    mutationFn: () => api<Qr>('/me/qr/rotate', { method: 'POST' }),
    onSuccess: (data) => qc.setQueryData(['qr'], data),
  })
  if (!qr.data) return <Spinner />
  return (
    <div className="mx-auto max-w-sm">
      <PageHeader title="My QR code" sub="Hold this up to the tablet at the front desk." />
      <Card className="flex flex-col items-center gap-4 p-8 text-center">
        <QRCodeSVG value={qr.data.token} size={240} level="M" marginSize={2} fgColor="#0d2e1d" />
        <div>
          <div className="font-display text-xl font-bold">{qr.data.name}</div>
          <div className="text-sm text-muted">{qr.data.club}</div>
        </div>
      </Card>
      <p className="mt-4 text-center text-xs text-muted">Lost your phone or shared a screenshot? Get a new code and the old one stops working.</p>
      <Button variant="ghost" className="mt-1 w-full" onClick={() => rotate.mutate()} disabled={rotate.isPending}>
        Get a new code
      </Button>
    </div>
  )
}
