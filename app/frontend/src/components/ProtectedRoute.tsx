import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useStoredToken } from '@/lib/auth-storage'

type Props = { children: ReactNode }

export function ProtectedRoute({ children }: Props) {
  const location = useLocation()
  const token = useStoredToken()

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}
