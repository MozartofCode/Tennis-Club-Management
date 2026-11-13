import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../../components/Shell'
import { Button, ErrorNote, Field, Input, Select } from '../../components/ui'
import { api } from '../../lib/api'
import { homeFor, useAuth, type User } from '../../lib/auth'

interface AuthOut {
  token: string
  user: User
}

function AuthLayout({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-court-800 p-10 text-white md:flex">
        <Logo light />
        <div>
          <p className="font-display text-4xl font-bold leading-tight">
            Run a fuller club
            <br />
            <span className="text-ball">with fewer phone calls.</span>
          </p>
          <p className="mt-4 max-w-sm text-court-100">
            Dynamic pricing, a self-running waitlist, churn alerts with reasons, and matchmaking that fills your quiet hours.
          </p>
        </div>
        <div className="text-xs text-court-200">Every AI suggestion explains itself. You stay in control.</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 md:hidden">
            <Logo />
          </div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-muted">{sub}</p>
          {children}
        </div>
      </div>
    </div>
  )
}

function useAuthSubmit(path: string) {
  const signIn = useAuth((s) => s.signIn)
  const navigate = useNavigate()
  return useMutation({
    mutationFn: (body: object) => api<AuthOut>(path, { body }),
    onSuccess: ({ token, user }) => {
      signIn(token, user)
      navigate(user.role === 'owner' && path.includes('owner') ? '/admin/setup' : homeFor(user.role))
    },
  })
}

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const submit = useAuthSubmit('/auth/login')
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit.mutate({ email, password })
  }
  return (
    <AuthLayout title="Welcome back" sub="Sign in to your club.">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorNote error={submit.error} />
        <Button className="w-full" disabled={submit.isPending}>
          {submit.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
      <DemoAccounts onPick={(e) => submit.mutate({ email: e, password: 'courtiq-demo' })} />
      <p className="mt-6 text-sm text-muted">
        New member? <Link className="font-semibold text-court-700" to="/join">Create your profile</Link>
        <br />
        Own a club? <Link className="font-semibold text-court-700" to="/start">Set up your club</Link>
      </p>
    </AuthLayout>
  )
}

function DemoAccounts({ onPick }: { onPick: (email: string) => void }) {
  const health = useQuery({ queryKey: ['health'], queryFn: () => api<{ demo: boolean }>('/health') })
  if (!health.data?.demo) return null
  const demos = [
    ['Owner', 'owner@courtiq.demo'],
    ['Front desk', 'desk@courtiq.demo'],
    ['Coach', 'coach@courtiq.demo'],
    ['Member', 'member@courtiq.demo'],
  ]
  return (
    <div className="mt-6 rounded-xl border border-line bg-white p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">Try the demo club as</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {demos.map(([label, email]) => (
          <Button key={email} type="button" size="sm" variant="secondary" onClick={() => onPick(email)}>
            {label}
          </Button>
        ))}
      </div>
    </div>
  )
}

export function MemberSignup() {
  const [params] = useSearchParams()
  const [form, setForm] = useState({ full_name: '', email: '', password: '', skill_level: '3.0' })
  const submit = useAuthSubmit('/auth/register')
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const club = params.get('club')
    submit.mutate({ ...form, skill_level: Number(form.skill_level), club_id: club ? Number(club) : null })
  }
  return (
    <AuthLayout title="Join your club" sub="Book courts, get your check-in QR code, and find players at your level.">
      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Full name">
          <Input required value={form.full_name} onChange={set('full_name')} autoComplete="name" />
        </Field>
        <Field label="Email">
          <Input type="email" required value={form.email} onChange={set('email')} autoComplete="email" />
        </Field>
        <Field label="Password" hint="At least 8 characters">
          <Input type="password" required minLength={8} value={form.password} onChange={set('password')} autoComplete="new-password" />
        </Field>
        <Field label="Your level (NTRP)" hint="Not sure? 2.5 = learning to rally, 3.5 = consistent club player, 4.5 = strong competitor.">
          <Select value={form.skill_level} onChange={set('skill_level')}>
            {[1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0].map((l) => (
              <option key={l} value={l.toFixed(1)}>
                {l.toFixed(1)}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorNote error={submit.error} />
        <Button className="w-full" disabled={submit.isPending}>
          Create my profile
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted">
        Did your club already add you? Sign up with the same email to claim your profile.
        <br />
        Already have a password? <Link className="font-semibold text-court-700" to="/login">Sign in</Link>
      </p>
    </AuthLayout>
  )
}

export function OwnerSignup() {
  const [form, setForm] = useState({ club_name: '', full_name: '', email: '', password: '' })
  const submit = useAuthSubmit('/auth/register-owner')
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })
  return (
    <AuthLayout title="Set up your club" sub="About 10 minutes: courts, hours, prices, coaches, and your member list.">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit.mutate(form)
        }}
        className="space-y-4"
      >
        <Field label="Club name">
          <Input required value={form.club_name} onChange={set('club_name')} />
        </Field>
        <Field label="Your name">
          <Input required value={form.full_name} onChange={set('full_name')} autoComplete="name" />
        </Field>
        <Field label="Email">
          <Input type="email" required value={form.email} onChange={set('email')} autoComplete="email" />
        </Field>
        <Field label="Password" hint="At least 8 characters">
          <Input type="password" required minLength={8} value={form.password} onChange={set('password')} autoComplete="new-password" />
        </Field>
        <ErrorNote error={submit.error} />
        <Button className="w-full" disabled={submit.isPending}>
          Create club
        </Button>
      </form>
    </AuthLayout>
  )
}
