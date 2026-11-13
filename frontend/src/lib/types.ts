import type { User } from './auth'

export interface Club {
  id: number
  name: string
  timezone: string
  city: string | null
  latitude: number | null
  longitude: number | null
  open_hour: number
  close_hour: number
  peak_hours: { weekday?: number[]; weekend?: number[] }
  currency: string
  base_price: number
  pricing_mode: 'off' | 'suggest' | 'on'
  min_price: number
  max_price: number
  max_surge_pct: number
  max_discount_pct: number
  waitlist_hold_minutes: number
  setup_complete: boolean
}

export interface Court {
  id: number
  name: string
  surface: string
  indoor: boolean
  has_lights: boolean
  is_active: boolean
}

export interface Plan {
  id: number
  name: string
  monthly_price: number
  court_discount_pct: number
  priority: number
  description: string | null
  is_active: boolean
}

export interface Membership {
  id: number
  plan_id: number
  plan: Plan
  start_date: string
  end_date: string
  status: string
  auto_renew: boolean
}

export interface Coach {
  id: number
  user_id: number
  specialties: string | null
  hourly_rate: number
  bio: string | null
  user: User
}

export interface PriceLine {
  label: string
  pct: number
}

export interface Booking {
  id: number
  court_id: number
  court_name: string
  user_id: number | null
  booker_name: string | null
  coach_id: number | null
  coach_name: string | null
  start_at: string
  end_at: string
  type: 'casual' | 'lesson' | 'match' | 'clinic'
  status: 'booked' | 'cancelled' | 'no_show' | 'completed'
  title: string | null
  capacity: number
  base_price: number
  price: number
  price_breakdown: PriceLine[]
  paid: boolean
  source: string
  players: { id: number; full_name: string; skill_level: number }[]
  checked_in: boolean
}

export interface Cell {
  court_id: number
  hour: number
  start_at: string
  status: 'free' | 'booked' | 'mine' | 'held' | 'offered' | 'past'
  price: number
  base_price: number
  suggested: number
  demand: number
  breakdown: PriceLine[]
}

export interface Availability {
  date: string
  hours: number[]
  courts: { id: number; name: string; surface: string; indoor: boolean }[]
  cells: Cell[]
}

export interface MemberRow {
  id: number
  full_name: string
  email: string
  phone: string | null
  skill_level: number
  plan: string | null
  membership_status: 'active' | 'expiring' | 'expired' | 'none'
  membership_end: string | null
  last_visit: string | null
  visits_30d: number
  upcoming_bookings: number
  churn_score: number | null
  churn_band: 'low' | 'medium' | 'high' | null
  created_at: string
}

export interface CheckInRow {
  id: number
  user_id: number
  member_name: string
  booking_id: number | null
  court_name: string | null
  method: string
  created_at: string
}

export interface MemberDetail {
  user: User
  membership: Membership | null
  memberships: Membership[]
  upcoming: Booking[]
  recent: Booking[]
  check_ins: CheckInRow[]
  stats: Record<string, number>
}

export interface Notification {
  id: number
  kind: string
  title: string
  body: string | null
  link: string | null
  read: boolean
  created_at: string
}

export interface WaitlistEntry {
  id: number
  user_id: number
  member_name: string
  date: string
  start_hour: number
  end_hour: number
  court_id: number | null
  status: 'waiting' | 'offered' | 'accepted' | 'declined' | 'expired' | 'left'
  priority_score: number
  priority_reasons: string[]
  offer_court_name: string | null
  offer_start_at: string | null
  offer_price: number | null
  offer_expires_at: string | null
  created_at: string
}

export interface Alternative {
  court_id: number
  court_name: string
  start_at: string
  price: number
  cheaper: boolean
}

export interface PricingWeek {
  mode: Club['pricing_mode']
  base_price: number
  days: string[]
  hours: number[]
  slots: { date: string; hour: number; forecast: number; booked: number; price: number; suggested: number; reasons: PriceLine[] }[]
  model: { kind: string; training_rows: number; mae: number | null }
}

export interface Simulation {
  weeks: number
  elasticity: number
  unmet_at_full: number
  flat_revenue: number
  dynamic_revenue: number
  flat_hours: number
  dynamic_hours: number
  peak_util_flat: number
  peak_util_dynamic: number
  offpeak_util_flat: number
  offpeak_util_dynamic: number
  by_hour: { hour: number; flat: number; dynamic: number }[]
}
