import type { KardexPage, StockPage, TipoMovimiento } from '../types'
import { httpClient } from './httpClient'

export const listarExistencias = (opciones: { bajoMinimo?: boolean; limit?: number } = {}) =>
  httpClient
    .get<StockPage>('/inventory', {
      params: { bajo_minimo: opciones.bajoMinimo ?? false, limit: opciones.limit ?? 200 },
    })
    .then((r) => r.data)

export interface FiltroKardex {
  productoId?: string
  tipo?: TipoMovimiento
  desde?: string
  hasta?: string
  offset?: number
  limit?: number
}

export const listarKardex = (f: FiltroKardex) =>
  httpClient
    .get<KardexPage>('/inventory/kardex', {
      params: {
        producto_id: f.productoId || undefined,
        tipo_movimiento: f.tipo || undefined,
        // `desde`/`hasta` llegan como fecha (YYYY-MM-DD); `hasta` incluye todo el día.
        desde: f.desde ? `${f.desde}T00:00:00Z` : undefined,
        hasta: f.hasta ? `${f.hasta}T23:59:59Z` : undefined,
        limit: f.limit ?? 25,
        offset: f.offset ?? 0,
      },
    })
    .then((r) => r.data)
