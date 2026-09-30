import type { RolItem, UsuarioCreate, UsuarioOut, UsuarioPage, UsuarioUpdate } from '../types'
import { httpClient } from './httpClient'

export interface FiltroUsuarios {
  q?: string
  rol?: string
  activo?: boolean
}

export const listarUsuarios = (filtro: FiltroUsuarios) =>
  httpClient
    .get<UsuarioPage>('/users', {
      params: { q: filtro.q || undefined, rol: filtro.rol || undefined, activo: filtro.activo, limit: 200 },
    })
    .then((r) => r.data)

export const listarRoles = () => httpClient.get<RolItem[]>('/users/roles').then((r) => r.data)

export const crearUsuario = (datos: UsuarioCreate) =>
  httpClient.post<UsuarioOut>('/users', datos).then((r) => r.data)

export const actualizarUsuario = (id: string, datos: UsuarioUpdate) =>
  httpClient.patch<UsuarioOut>(`/users/${id}`, datos).then((r) => r.data)

export const cambiarEstadoUsuario = (id: string, activo: boolean) =>
  httpClient.patch<UsuarioOut>(`/users/${id}/status`, { activo }).then((r) => r.data)
