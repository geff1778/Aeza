/** Auth context: holds the current session and exposes login/logout.
 * The session lives in an HttpOnly cookie; only the CSRF token is readable. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, api, UnauthorizedError } from '../lib/api'
import type { Me } from '../lib/types'

interface AuthState {
  user: Me | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  isAdmin: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<Me>('/auth/me')
      setUser(me)
    } catch (error) {
      if (error instanceof UnauthorizedError) {
        setUser(null)
      } else if (error instanceof ApiError) {
        setUser(null)
      }
    }
  }, [])

  useEffect(() => {
    void refresh().finally(() => setLoading(false))
  }, [refresh])

  const login = useCallback(async (username: string, password: string) => {
    const me = await api.post<Me>('/auth/login', { username, password })
    setUser(me)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, logout, refresh, isAdmin: user?.role === 'admin' }),
    [user, loading, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
