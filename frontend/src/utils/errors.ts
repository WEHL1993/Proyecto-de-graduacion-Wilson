import axios from 'axios'
import type { ApiError } from '../types'

export function apiError(e: unknown): ApiError | null {
  if (axios.isAxiosError(e) && e.response?.data && typeof e.response.data === 'object') {
    const d = e.response.data as Partial<ApiError> & { detail?: unknown }
    if (d.codigo) return d as ApiError
  }
  return null
}

export function mensajeError(e: unknown): string {
  const api = apiError(e)
  if (api) return api.mensaje
  if (axios.isAxiosError(e)) {
    if (!e.response) return 'No se pudo contactar al servidor.'
    if (e.response.status === 422) return 'Los datos enviados no son válidos.'
    return `Error ${e.response.status} del servidor.`
  }
  return e instanceof Error ? e.message : 'Error inesperado.'
}

export function esStatus(e: unknown, status: number): boolean {
  return axios.isAxiosError(e) && e.response?.status === status
}
