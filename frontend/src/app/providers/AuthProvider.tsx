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
  /** ¿La pantalla (clave de `pantallas` en la BD) figura en el menú autorizado del usuario? */
  puedeVer: (clave: string) => boolean
  /** Relee roles, permisos y menú de la BD (cambios de la matriz sin volver a iniciar sesión). */
  refrescar: () => Promise<void>
}

/** Cada cuánto se revalida el acceso mientras la pestaña está abierta. */
const REFRESCO_MS = 60_000

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

  const refrescar = useCallback(async () => {
    try {
      const vigente = await authApi.sesionVigente()
      setSesion((actual) => {
        if (!actual) return actual
        const nueva: Sesion = {
          ...actual,
          usuario: {
            id: vigente.id,
            nombre_completo: vigente.nombre_completo,
            roles: vigente.roles,
            permisos: vigente.permisos,
            menu: vigente.menu,
            pantalla_inicio: vigente.pantalla_inicio ?? null,
          },
        }
        guardarSesion(nueva)
        return nueva
      })
    } catch {
      /* un 401 lo atiende el interceptor; otros errores conservan el acceso en memoria */
    }
  }, [])

  // El acceso vive en la BD: se revalida al abrir, al volver a la pestaña y cada minuto.
  const autenticado = sesion !== null
  useEffect(() => {
    if (!autenticado) return
    void refrescar()
    const alVolver = () => document.visibilityState === 'visible' && void refrescar()
    document.addEventListener('visibilitychange', alVolver)
    const t = window.setInterval(() => void refrescar(), REFRESCO_MS)
    return () => {
      document.removeEventListener('visibilitychange', alVolver)
      window.clearInterval(t)
    }
  }, [autenticado, refrescar])

  const login = useCallback(async (email: string, password: string) => {
    const r = await authApi.login(email, password)
    const nueva: Sesion = {
      token: r.access_token,
      expiraEn: Date.now() + r.expires_in * 1000,
      usuario: { ...r.usuario, pantalla_inicio: r.usuario.pantalla_inicio ?? null },
    }
    guardarSesion(nueva)
    setSesionExpirada(false)
    setSesion(nueva)
  }, [])

  const valor = useMemo<AuthContexto>(() => {
    const permisos = new Set(sesion?.usuario.permisos ?? [])
    const pantallas = new Set((sesion?.usuario.menu ?? []).map((p) => p.clave))
    return {
      usuario: sesion?.usuario ?? null,
      sesionExpirada,
      login,
      logout,
      can: (p) => permisos.has(p),
      canAny: (ps) => ps.some((p) => permisos.has(p)),
      puedeVer: (clave) => pantallas.has(clave),
      refrescar,
    }
  }, [sesion, sesionExpirada, login, logout, refrescar])

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContexto {
  const ctx = useContext(Contexto)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
