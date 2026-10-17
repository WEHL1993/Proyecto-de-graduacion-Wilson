import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../services/rbacApi'
import type { RolUpdate } from '../types'

export const useMatriz = () =>
  useQuery({ queryKey: ['rbac', 'matriz'], retry: false, queryFn: api.obtenerMatriz })

export const useAccesoUsuario = (usuarioId: string) =>
  useQuery({
    queryKey: ['rbac', 'acceso', usuarioId],
    enabled: !!usuarioId,
    retry: false,
    queryFn: () => api.obtenerAccesoUsuario(usuarioId),
  })

export function useRbacActions() {
  const cliente = useQueryClient()
  // Un cambio de matriz altera roles, el acceso de los usuarios y el menú propio.
  const refrescar = () => {
    void cliente.invalidateQueries({ queryKey: ['rbac'] })
    void cliente.invalidateQueries({ queryKey: ['roles'] })
    void cliente.invalidateQueries({ queryKey: ['usuarios'] })
  }
  return {
    guardarPermisos: useMutation({
      mutationFn: (a: { rolId: number; permisos: string[] }) => api.reemplazarPermisosRol(a.rolId, a.permisos),
      onSuccess: refrescar,
    }),
    actualizarRol: useMutation({
      mutationFn: (a: { rolId: number; datos: RolUpdate }) => api.actualizarRol(a.rolId, a.datos),
      onSuccess: refrescar,
    }),
  }
}
