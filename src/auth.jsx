import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { auth } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    auth.restore().then(setUser).catch(() => setUser(null)).finally(() => setRestoring(false))
    const clear = () => setUser(null)
    window.addEventListener('pivot:session-expired', clear)
    return () => window.removeEventListener('pivot:session-expired', clear)
  }, [])

  const value = useMemo(() => ({ user, restoring, login: auth.login, logout: async () => { await auth.logout(); setUser(null) } }), [user, restoring])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider.')
  return context
}
