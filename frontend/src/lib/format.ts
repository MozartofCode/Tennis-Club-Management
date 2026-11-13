export function money(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: value % 1 === 0 ? 0 : 2 }).format(value)
}

export function pct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

// Booking times are club-local wall-clock strings ("2026-11-12T18:00:00"); parse without timezone shifts.
export function parseLocal(iso: string): Date {
  const [d, t = '00:00:00'] = iso.split('T')
  const [y, m, day] = d.split('-').map(Number)
  const [hh, mm] = t.split(':').map(Number)
  return new Date(y, m - 1, day, hh, mm)
}

export function toLocalIso(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}:00`
}

export function dateKey(date: Date): string {
  return toLocalIso(date).slice(0, 10)
}

export function hourLabel(hour: number): string {
  const h = hour % 12 === 0 ? 12 : hour % 12
  return `${h}${hour < 12 ? 'am' : 'pm'}`
}

export function dayLabel(iso: string): string {
  return parseLocal(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

export function timeLabel(iso: string): string {
  return parseLocal(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

export function relativeDays(iso: string): string {
  const days = Math.round((Date.now() - parseLocal(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}
