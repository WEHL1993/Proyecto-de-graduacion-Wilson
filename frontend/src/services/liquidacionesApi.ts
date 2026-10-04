import type {
  EstadoLiquidacion,
  LiquidacionConfig,
  LiquidacionRequest,
  LiquidacionResponse,
  ListadoLiquidaciones,
  PrecargaResponse,
} from '../types'
import { httpClient } from './httpClient'

export interface FiltroLiquidaciones {
  desde?: string
  hasta?: string
  ruta_id?: string
  estado?: EstadoLiquidacion | ''
  limit: number
  offset: number
}

export const precargar = (fecha: string, rutaId: string) =>
  httpClient
    .get<PrecargaResponse>('/liquidaciones/precarga', { params: { fecha, ruta_id: rutaId } })
    .then((r) => r.data)

export const guardarLiquidacion = (cuerpo: LiquidacionRequest) =>
  httpClient.post<LiquidacionResponse>('/liquidaciones', cuerpo).then((r) => r.data)

export const cerrarLiquidacion = (id: string) =>
  httpClient.post<LiquidacionResponse>(`/liquidaciones/${id}/cerrar`).then((r) => r.data)

export const corregirLiquidacion = (id: string, cuerpo: LiquidacionRequest, motivo: string) =>
  httpClient
    .post<LiquidacionResponse>(`/liquidaciones/${id}/corregir`, { ...cuerpo, motivo })
    .then((r) => r.data)

export const anularLiquidacion = (id: string, motivo: string) =>
  httpClient.post<LiquidacionResponse>(`/liquidaciones/${id}/anular`, { motivo }).then((r) => r.data)

export const listarLiquidaciones = (f: FiltroLiquidaciones) =>
  httpClient
    .get<ListadoLiquidaciones>('/liquidaciones', {
      params: {
        limit: f.limit,
        offset: f.offset,
        estado: f.estado || undefined,
        desde: f.desde || undefined,
        hasta: f.hasta || undefined,
        ruta_id: f.ruta_id || undefined,
      },
    })
    .then((r) => r.data)

export const obtenerLiquidacion = (id: string) =>
  httpClient.get<LiquidacionResponse>(`/liquidaciones/${id}`).then((r) => r.data)

export const obtenerConfigLiquidacion = () =>
  httpClient.get<LiquidacionConfig>('/liquidaciones/config').then((r) => r.data)

export const guardarConfigLiquidacion = (config: LiquidacionConfig) =>
  httpClient.put<LiquidacionConfig>('/liquidaciones/config', config).then((r) => r.data)
