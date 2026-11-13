import type { NavItem } from '../components/Shell'

export const adminNav: NavItem[] = [
  { to: '/admin', label: 'Today', icon: '◎', end: true },
  { to: '/admin/calendar', label: 'Court calendar', icon: '▦' },
  { to: '/admin/members', label: 'Members', icon: '☺' },
  { to: '/admin/checkins', label: 'Check-ins', icon: '✓' },
  { to: '/admin/pricing', label: 'Dynamic pricing', icon: '$' },
  { to: '/admin/waitlist', label: 'Waitlist', icon: '⏳' },
  { to: '/admin/retention', label: 'Retention', icon: '♥' },
  { to: '/admin/matchmaking', label: 'Matchmaking', icon: '⇄' },
  { to: '/admin/setup', label: 'Club setup', icon: '⚙' },
]

export const memberNav: NavItem[] = [
  { to: '/app', label: 'Home', icon: '◎', end: true },
  { to: '/app/book', label: 'Book a court', icon: '▦' },
  { to: '/app/matches', label: 'Find a match', icon: '⇄' },
  { to: '/app/qr', label: 'My QR code', icon: '▣' },
  { to: '/app/offers', label: 'Offers', icon: '★' },
  { to: '/app/profile', label: 'Profile', icon: '☺' },
]

export const coachNav: NavItem[] = [{ to: '/coach', label: 'My schedule', icon: '▦', end: true }]
