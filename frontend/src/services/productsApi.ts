import type { ProductoCreate, ProductoOut, ProductoPage, ProductoUpdate } from '../types'
import { httpClient } from './httpClient'

export interface FiltroProductos {
  q?: string
  /** `true` = activos, `false` = dados de baja (baja lógica). */
  activo: boolean
  categoriaId?: string
  limit?: number
  offset?: number
}

export const listarProductos = (f: FiltroProductos) =>
  httpClient
    .get<ProductoPage>('/products', {
      params: {
        q: f.q || undefined,
        activo: f.activo,
        categoria_id: f.categoriaId || undefined,
        limit: f.limit ?? 25,
        offset: f.offset ?? 0,
      },
    })
    .then((r) => r.data)

export const crearProducto = (datos: ProductoCreate) =>
  httpClient.post<ProductoOut>('/products', datos).then((r) => r.data)

export const actualizarProducto = (id: string, datos: ProductoUpdate) =>
  httpClient.patch<ProductoOut>(`/products/${id}`, datos).then((r) => r.data)

export const darDeBajaProducto = (id: string) => httpClient.delete(`/products/${id}`).then(() => undefined)

export const reactivarProducto = (id: string) =>
  httpClient.post<ProductoOut>(`/products/${id}/reactivate`).then((r) => r.data)
