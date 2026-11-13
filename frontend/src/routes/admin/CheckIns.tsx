import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Empty, PageHeader, Spinner } from '../../components/ui'
import { api } from '../../lib/api'
import { dateKey, timeLabel } from '../../lib/format'
import type { CheckInRow } from '../../lib/types'
import { DateNav } from './Calendar'

export function CheckIns() {
  const [day, setDay] = useState(() => new Date())
  const key = dateKey(day)
  const log = useQuery({ queryKey: ['checkins', key], queryFn: () => api<CheckInRow[]>(`/checkin?day=${key}`), refetchInterval: 15_000 })
  return (
    <div>
      <PageHeader
        title="Check-ins"
        sub={`${log.data?.length ?? 0} visits on this day`}
        action={
          <div className="flex flex-wrap gap-2">
            <DateNav day={day} setDay={setDay} />
            <Link to="/kiosk" target="_blank">
              <Button variant="ball">Open check-in kiosk ↗</Button>
            </Link>
          </div>
        }
      />
      {log.isLoading ? (
        <Spinner />
      ) : !log.data?.length ? (
        <Empty title="No check-ins yet">Open the kiosk on a tablet at the front desk. Members scan the QR code in their app.</Empty>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-white">
          <table className="w-full text-sm">
            <tbody>
              {log.data.map((c) => (
                <tr key={c.id} className="border-t border-line first:border-0">
                  <td className="w-24 p-3 font-semibold">{timeLabel(c.created_at)}</td>
                  <td className="p-3">
                    <Link className="font-semibold text-court-800 hover:underline" to={`/admin/members/${c.user_id}`}>
                      {c.member_name}
                    </Link>
                  </td>
                  <td className="p-3 text-muted">{c.court_name ?? 'No booking'}</td>
                  <td className="p-3 text-right">
                    <Badge tone={c.method === 'qr' ? 'green' : 'neutral'}>{c.method === 'qr' ? 'QR' : 'Manual'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
