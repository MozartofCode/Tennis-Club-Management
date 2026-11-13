import { Link, Navigate } from 'react-router-dom'
import { Logo } from '../../components/Shell'
import { homeFor, useAuth } from '../../lib/auth'

const features = [
  {
    title: 'Prices that follow demand',
    body: 'Peak hours earn more, quiet hours fill up with automatic discounts. Every price shows its reasons, inside limits you set.',
  },
  {
    title: 'A waitlist that runs itself',
    body: 'When someone cancels, the slot is offered to the right member with a 15-minute hold. No phone tree.',
  },
  {
    title: 'Know who is about to leave',
    body: 'Members at risk are flagged with plain-English reasons, and a ready-to-send offer you approve.',
  },
  {
    title: 'Matches at the right level',
    body: 'Members get matched with similar players and a court is booked for them, preferably in off-peak hours.',
  },
]

export function Landing() {
  const user = useAuth((s) => s.user)
  if (user) return <Navigate to={homeFor(user.role)} replace />
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <Link to="/login" className="text-sm font-semibold text-court-700">
          Sign in
        </Link>
      </header>
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-10 md:pt-20">
        <p className="mb-3 inline-block rounded-full bg-ball-soft px-3 py-1 text-xs font-bold uppercase tracking-wide text-court-800">
          Tennis club management
        </p>
        <h1 className="max-w-3xl text-4xl font-bold leading-[1.05] md:text-6xl">
          Your courts, fuller. <span className="text-court-600">Your members, staying.</span>
        </h1>
        <p className="mt-5 max-w-xl text-lg text-muted">
          CourtIQ handles bookings, QR check-in and memberships, then uses simple, explainable AI to price courts, refill cancellations, spot churn early and match players.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/start" className="rounded-xl bg-court-800 px-5 py-3 font-semibold text-white hover:bg-court-700">
            Set up your club
          </Link>
          <Link to="/join" className="rounded-xl border border-line bg-white px-5 py-3 font-semibold hover:bg-court-50">
            I'm a member
          </Link>
        </div>
      </section>
      <section className="mx-auto grid max-w-6xl gap-4 px-4 pb-20 md:grid-cols-2">
        {features.map((f) => (
          <div key={f.title} className="rounded-2xl border border-line bg-white p-6">
            <h2 className="text-lg font-bold">{f.title}</h2>
            <p className="mt-2 text-sm text-muted">{f.body}</p>
          </div>
        ))}
      </section>
    </div>
  )
}
