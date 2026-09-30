import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import * as authApi from '../../services/authApi'
import { registrarAlExpirar } from '../../services/httpClient'
import { borrarSesion, guardarSesion, leerSesion } from '../../utils/session'
import type { Sesion } from '../../utils/session'

interface AuthContexto {
  usuario: Sesion['usuario'] | null
  sesionExpirada: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  can: (permiso: string) => boolean
  canAny: (permisos: readonly string[]) => boolean
}

const Contexto = createContext<AuthContexto | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(() => leerSesion())
  const [sesionExpirada, setSesionExpirada] = useState(false)

  const logout = useCallback(() => {
    borrarSesion()
    setSesion(null)
  }, [])

  useEffect(() => {
    registrarAlExpirar(() => {
      setSesion(null)
      setSesionExpirada(true)
    })
    return () => registrarAlExpirar(null)
  }, [])

  // Cierra la sesión cuando vence el JWT, aunque la pestaña permanezca abierta.
  useEffect(() => {
    if (!sesion) return
    const restante = sesion.expiraEn - Date.now()
    const t = window.setTimeout(
      () => {
        logout()
        setSesionExpirada(true)
      },
      Math.max(restante, 0),
    )
    return () => window.clearTimeout(t)
  }, [sesion, logout])

  const login = useCallback(async (email: string, password: string) => {
    const r = await authApi.login(email, password)
    const nueva: Sesion = {
      token: r.access_token,
      expiraEn: Date.now() + r.expires_in * 1000,
      usuario: r.usuario,
    }
    guardarSesion(nueva)
    setSesionExpirada(false)
    setSesion(nueva)
  }, [])

  const valor = useMemo<AuthContexto>(() => {
    const permisos = new Set(sesion?.usuario.permisos ?? [])
    return {
      usuario: sesion?.usuario ?? null,
      sesionExpirada,
      login,
      logout,
      can: (p) => permisos.has(p),
      canAny: (ps) => ps.some((p) => permisos.has(p)),
    }
  }, [sesion, sesionExpirada, login, logout])

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContexto {
  const ctx = useContext(Contexto)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
