import clsx from 'clsx'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export interface NavItem {
  to: string
  label: string
  icon: string
  end?: boolean
}

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className={clsx('inline-flex items-center gap-2 font-display text-lg font-bold', light ? 'text-white' : 'text-court-800')}>
      <svg viewBox="0 0 64 64" className="h-7 w-7" aria-hidden>
        <rect width="64" height="64" rx="14" fill={light ? '#d4f04c' : '#14432a'} />
        <circle cx="32" cy="32" r="16" fill={light ? '#14432a' : '#d4f04c'} />
        <path d="M19 22c8 4 8 16 0 20M45 22c-8 4-8 16 0 20" stroke={light ? '#d4f04c' : '#14432a'} strokeWidth="3" fill="none" />
      </svg>
      CourtIQ
    </span>
  )
}

export function Shell({ nav, title }: { nav: NavItem[]; title: string }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const links = (
    <nav className="flex flex-col gap-0.5">
      {nav.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition',
              isActive ? 'bg-ball text-court-900' : 'text-court-100 hover:bg-court-700',
            )
          }
        >
          <span className="w-5 text-center" aria-hidden>
            {item.icon}
          </span>
          {item.label}
        </NavLink>
      ))}
    </nav>
  )

  const footer = (
    <div className="mt-auto border-t border-court-700 pt-4 text-sm text-court-100">
      <div className="font-semibold text-white">{user?.full_name}</div>
      <div className="text-xs capitalize text-court-200">{user?.role}</div>
      <button
        className="mt-2 text-xs font-semibold text-ball hover:underline"
        onClick={() => {
          signOut()
          navigate('/login')
        }}
      >
        Sign out
      </button>
    </div>
  )

  return (
    <div className="min-h-screen md:flex">
      <aside className="hidden w-60 shrink-0 flex-col gap-6 bg-court-800 p-4 md:sticky md:top-0 md:flex md:h-screen">
        <div>
          <Logo light />
          <div className="mt-1 text-xs text-court-200">{title}</div>
        </div>
        {links}
        {footer}
      </aside>

      <header className="sticky top-0 z-20 flex items-center justify-between bg-court-800 px-4 py-3 md:hidden">
        <Logo light />
        <button className="rounded-lg px-2 py-1 text-sm font-semibold text-ball" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Close' : 'Menu'}
        </button>
      </header>
      {open && (
        <div className="fixed inset-x-0 top-[52px] z-20 flex flex-col gap-4 bg-court-800 p-4 md:hidden">
          {links}
          {footer}
        </div>
      )}

      <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  )
}
