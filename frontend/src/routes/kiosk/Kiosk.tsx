import { Html5Qrcode } from 'html5-qrcode'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '../../components/Shell'
import { api } from '../../lib/api'
import type { Booking } from '../../lib/types'

interface ScanResult {
  status: 'welcome' | 'no_booking' | 'already'
  member_name: string
  membership: string | null
  membership_ok: boolean
  booking: Booking | null
  message: string
}

type View = { kind: 'idle' } | { kind: 'result'; result: ScanResult } | { kind: 'error'; message: string }

export function Kiosk() {
  const [view, setView] = useState<View>({ kind: 'idle' })
  const [camera, setCamera] = useState<'starting' | 'on' | 'off'>('starting')
  const busy = useRef(false)
  const typed = useRef<HTMLInputElement>(null)

  const submit = useCallback(async (token: string) => {
    if (busy.current || !token.trim()) return
    busy.current = true
    try {
      const result = await api<ScanResult>('/checkin/scan', { body: { token } })
      setView({ kind: 'result', result })
    } catch (e) {
      setView({ kind: 'error', message: e instanceof Error ? e.message : 'Something went wrong' })
    }
    setTimeout(() => {
      busy.current = false
      setView({ kind: 'idle' })
      typed.current?.focus()
    }, 4500)
  }, [])

  useEffect(() => {
    const scanner = new Html5Qrcode('qr-reader', { verbose: false })
    let running = false
    scanner
      .start({ facingMode: 'user' }, { fps: 8, qrbox: { width: 260, height: 260 } }, (text) => submit(text), () => undefined)
      .then(() => {
        running = true
        setCamera('on')
      })
      .catch(() => setCamera('off'))
    return () => {
      if (running) scanner.stop().catch(() => undefined)
    }
  }, [submit])

  const tone =
    view.kind === 'error' ? 'bg-clay-500' : view.kind === 'result' ? (view.result.status === 'no_booking' && !view.result.membership_ok ? 'bg-amber-500' : 'bg-court-600') : 'bg-court-800'

  return (
    <div className={`flex min-h-screen flex-col text-white transition-colors ${tone}`}>
      <header className="flex items-center justify-between p-5">
        <Logo light />
        <Link to="/admin/checkins" className="text-sm font-semibold text-court-100">
          Exit kiosk
        </Link>
      </header>
      <main className="flex flex-1 flex-col items-center justify-center gap-8 p-6 text-center">
        <div className={view.kind === 'idle' ? '' : 'hidden'}>
          <h1 className="text-4xl font-bold md:text-5xl">Scan to check in</h1>
          <p className="mt-2 text-court-100">Open CourtIQ on your phone → My QR code, and hold it up to the camera.</p>
        </div>
        <div className={`overflow-hidden rounded-3xl bg-black/30 ${view.kind === 'idle' ? '' : 'hidden'}`}>
          <div id="qr-reader" className="w-[320px] max-w-[80vw]" />
          {camera === 'off' && <p className="max-w-xs p-6 text-sm text-court-100">Camera not available. Use a USB scanner or type the code below.</p>}
        </div>

        {view.kind === 'result' && (
          <div>
            <div className="text-7xl" aria-hidden>
              {view.result.status === 'welcome' ? '🎾' : view.result.status === 'already' ? '👍' : '👋'}
            </div>
            <h1 className="mt-4 text-4xl font-bold md:text-5xl">{view.result.message}</h1>
            {view.result.booking && (
              <p className="mt-3 text-xl">
                {view.result.booking.court_name}
                {view.result.booking.coach_name ? ` with ${view.result.booking.coach_name}` : ''}
                {!view.result.booking.paid && ' · please pay at the desk'}
              </p>
            )}
            {!view.result.membership_ok && <p className="mt-3 text-lg font-semibold">No active membership: please see the front desk.</p>}
          </div>
        )}
        {view.kind === 'error' && (
          <div>
            <h1 className="text-4xl font-bold">Couldn't check you in</h1>
            <p className="mt-3 text-lg">{view.message}</p>
          </div>
        )}

        <form
          className={view.kind === 'idle' ? '' : 'invisible'}
          onSubmit={(e) => {
            e.preventDefault()
            const el = typed.current
            if (el) {
              submit(el.value)
              el.value = ''
            }
          }}
        >
          <input ref={typed} autoFocus placeholder="Or type / scan code here" className="w-72 rounded-xl bg-white/15 px-4 py-2 text-center text-white placeholder:text-court-100 outline-none" aria-label="Check-in code" />
        </form>
      </main>
    </div>
  )
}
