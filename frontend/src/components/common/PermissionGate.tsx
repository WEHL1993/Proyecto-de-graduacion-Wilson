import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../app/providers/AuthProvider'

interface Props {
  /** Se exige alguno de estos permisos (`recurso:accion`); vacío = solo sesión iniciada (modo ruta). */
  anyOf: readonly string[]
  children: ReactNode
  /** Qué mostrar sin permiso (por defecto nada). */
  fallback?: ReactNode
  /** Modo ruta: sin sesión → /login; sin permiso → /acceso-denegado (TC-RBAC-04). */
  guardRoute?: boolean
}

export function PermissionGate({ anyOf, children, fallback = null, guardRoute = false }: Props) {
  const { usuario, canAny } = useAuth()
  const location = useLocation()

  if (guardRoute) {
    if (!usuario) return <Navigate to="/login" replace state={{ desde: location.pathname }} />
    if (anyOf.length > 0 && !canAny(anyOf)) return <Navigate to="/acceso-denegado" replace />
    return <>{children}</>
  }
  return canAny(anyOf) ? <>{children}</> : <>{fallback}</>
}
