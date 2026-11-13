import { create } from 'zustand'

export type Role = 'owner' | 'staff' | 'coach' | 'member'

export interface User {
  id: number
  club_id: number | null
  email: string
  role: Role
  full_name: string
  phone: string | null
  skill_level: number
  availability: string[]
  play_style: string | null
  goals: string | null
  preferred_format: string
  league_opt_in: boolean
  matches_played: number
  created_at: string
}

interface AuthState {
  token: string | null
  user: User | null
  signIn: (token: string, user: User) => void
  setUser: (user: User) => void
  signOut: () => void
}

const KEY = 'courtiq.auth'

function load(): { token: string | null; user: User | null } {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    // storage unavailable (private mode); fall through to signed out
  }
  return { token: null, user: null }
}

function save(token: string | null, user: User | null) {
  try {
    if (token) localStorage.setItem(KEY, JSON.stringify({ token, user }))
    else localStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

export const useAuth = create<AuthState>((set, get) => ({
  ...load(),
  signIn: (token, user) => {
    save(token, user)
    set({ token, user })
  },
  setUser: (user) => {
    save(get().token, user)
    set({ user })
  },
  signOut: () => {
    save(null, null)
    set({ token: null, user: null })
  },
}))

export function homeFor(role: Role): string {
  if (role === 'owner' || role === 'staff') return '/admin'
  if (role === 'coach') return '/coach'
  return '/app'
}
