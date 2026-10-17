import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'

interface Props {
  /** Se exige alguno de estos permisos (`recurso:accion`); vacío = solo sesión iniciada (modo ruta). */
  anyOf?: readonly string[]
  /** Clave de la pantalla en la BD (`pantallas.clave`): se exige que figure en el menú autorizado. */
  pantalla?: string
  children: ReactNode
  /** Qué mostrar sin permiso (por defecto nada). */
  fallback?: ReactNode
  /** Modo ruta: sin sesión → /login; sin permiso → /acceso-denegado (TC-RBAC-04). */
  guardRoute?: boolean
}

export function PermissionGate({ anyOf = [], pantalla, children, fallback = null, guardRoute = false }: Props) {
  const { usuario, canAny, puedeVer } = useAuth()
  const location = useLocation()
  const autorizado = pantalla
    ? puedeVer(pantalla)
    : (guardRoute && anyOf.length === 0) || canAny(anyOf)

  if (guardRoute) {
    if (!usuario) return <Navigate to="/login" replace state={{ desde: location.pathname }} />
    if (!autorizado) return <Navigate to="/acceso-denegado" replace />
    return <>{children}</>
  }
  return autorizado ? <>{children}</> : <>{fallback}</>
}
