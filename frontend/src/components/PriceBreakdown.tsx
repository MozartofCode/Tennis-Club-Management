import clsx from 'clsx'
import { money } from '../lib/format'
import type { PriceLine } from '../lib/types'

export function PriceBreakdown({ base, price, lines, currency }: { base: number; price: number; lines: PriceLine[]; currency?: string }) {
  return (
    <div className="rounded-xl bg-paper p-3 text-sm">
      <div className="flex justify-between text-muted">
        <span>Standard court-hour</span>
        <span>{money(base, currency)}</span>
      </div>
      {lines.map((l) => (
        <div key={l.label} className="mt-1 flex justify-between">
          <span>{l.label}</span>
          <span className={clsx('font-semibold', l.pct > 0 ? 'text-clay-600' : 'text-court-600')}>
            {l.pct > 0 ? '+' : ''}
            {l.pct}%
          </span>
        </div>
      ))}
      <div className="mt-2 flex justify-between border-t border-line pt-2 font-bold">
        <span>You pay</span>
        <span>{money(price, currency)}</span>
      </div>
    </div>
  )
}
