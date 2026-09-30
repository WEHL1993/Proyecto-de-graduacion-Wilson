import axios from 'axios'
import type { EtlResult, EtlValidationError, LotePage } from '../types'
import { httpClient } from './httpClient'

export type ModoCarga = 'estricto' | 'parcial'

export interface OpcionesCarga {
  modo: ModoCarga
  hoja?: string
  periodo?: string
}

// Timeout ampliado: archivos de hasta 20 MB se validan completos antes de responder.
const TIMEOUT_CARGA_MS = 5 * 60_000

export const subirExcel = (
  archivo: File,
  opciones: OpcionesCarga,
  alProgreso: (porcentaje: number) => void,
) => {
  const cuerpo = new FormData()
  cuerpo.append('file', archivo)
  cuerpo.append('modo', opciones.modo)
  if (opciones.hoja) cuerpo.append('hoja', opciones.hoja)
  if (opciones.periodo) cuerpo.append('periodo', opciones.periodo)
  return httpClient
    .post<EtlResult>('/etl/upload-excel', cuerpo, {
      timeout: TIMEOUT_CARGA_MS,
      onUploadProgress: (e) => e.total && alProgreso(Math.round((e.loaded * 100) / e.total)),
    })
    .then((r) => r.data)
}

/** Cuerpo 422 del ETL (`EtlValidationError`) si el error lo es; `null` en otro caso. */
export function errorDeValidacion(e: unknown): EtlValidationError | null {
  if (!axios.isAxiosError(e) || e.response?.status !== 422) return null
  const d = e.response.data as Partial<EtlValidationError> | undefined
  return d && Array.isArray(d.errores) && d.lote_id ? (d as EtlValidationError) : null
}

export const listarLotes = (limit: number, offset: number) =>
  httpClient.get<LotePage>('/etl/batches', { params: { limit, offset } }).then((r) => r.data)
