import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { Club } from './types'

export function useClub() {
  return useQuery({ queryKey: ['club'], queryFn: () => api<Club>('/club') })
}
