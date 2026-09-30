import { useAuth } from '../app/providers/AuthProvider'

export function usePermissions() {
  const { can, canAny, usuario } = useAuth()
  return { can, canAny, roles: usuario?.roles ?? [] }
}
