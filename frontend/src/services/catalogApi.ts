import type { AlertItem, AlertList, CategoriaItem, ProveedorItem, RouteItem } from '../types'
import { httpClient } from './httpClient'

export const listarRutas = () => httpClient.get<RouteItem[]>('/catalog/routes').then((r) => r.data)

export const listarCategorias = () =>
  httpClient.get<CategoriaItem[]>('/catalog/categories').then((r) => r.data)

export const listarProveedores = () =>
  httpClient.get<ProveedorItem[]>('/catalog/suppliers').then((r) => r.data)

// El servidor ya filtra por los permisos del usuario (qué tipos de alerta le corresponden).
export const listarAlertas = () =>
  httpClient
    .get<AlertList>('/alerts', { params: { estado: 'abierta', limit: 20 } })
    .then((r) => r.data)

export const reconocerAlerta = (id: string) =>
  httpClient.patch<AlertItem>(`/alerts/${id}/acknowledge`).then((r) => r.data)
