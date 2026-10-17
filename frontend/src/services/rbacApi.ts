import type { AccesoUsuario, MatrizAcceso, RolMatriz, RolUpdate } from '../types'
import { httpClient } from './httpClient'

export const obtenerMatriz = () => httpClient.get<MatrizAcceso>('/rbac/matrix').then((r) => r.data)

export const reemplazarPermisosRol = (rolId: number, permisos: string[]) =>
  httpClient.put<RolMatriz>(`/rbac/roles/${rolId}/permissions`, { permisos }).then((r) => r.data)

export const actualizarRol = (rolId: number, datos: RolUpdate) =>
  httpClient.patch<RolMatriz>(`/rbac/roles/${rolId}`, datos).then((r) => r.data)

export const obtenerAccesoUsuario = (usuarioId: string) =>
  httpClient.get<AccesoUsuario>(`/rbac/users/${usuarioId}/access`).then((r) => r.data)
