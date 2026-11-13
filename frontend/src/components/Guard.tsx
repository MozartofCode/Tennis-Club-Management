import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { homeFor, useAuth, type Role } from '../lib/auth'

export function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const user = useAuth((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}
