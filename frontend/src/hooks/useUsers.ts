import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../services/usersApi'
import type { FiltroUsuarios } from '../services/usersApi'
import type { UsuarioCreate, UsuarioUpdate } from '../types'

export const useUsuarios = (filtro: FiltroUsuarios) =>
  useQuery({
    queryKey: ['usuarios', filtro],
    retry: false,
    queryFn: () => api.listarUsuarios(filtro),
  })

export const useRoles = () =>
  useQuery({ queryKey: ['roles'], staleTime: 5 * 60_000, retry: false, queryFn: api.listarRoles })

export function useUsuarioActions() {
  const cliente = useQueryClient()
  const opciones = { onSuccess: () => void cliente.invalidateQueries({ queryKey: ['usuarios'] }) }
  return {
    crear: useMutation({ mutationFn: (d: UsuarioCreate) => api.crearUsuario(d), ...opciones }),
    actualizar: useMutation({
      mutationFn: (a: { id: string; datos: UsuarioUpdate }) => api.actualizarUsuario(a.id, a.datos),
      ...opciones,
    }),
    cambiarEstado: useMutation({
      mutationFn: (a: { id: string; activo: boolean }) => api.cambiarEstadoUsuario(a.id, a.activo),
      ...opciones,
    }),
  }
}
