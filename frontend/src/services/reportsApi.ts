import type { ComisionReporte, RotacionReporte, VentasProyeccionReporte } from '../types'
import { httpClient } from './httpClient'

export interface FiltroReportes {
  desde?: string
  hasta?: string
  rutaId?: string
}

const rango = (f: FiltroReportes) => ({
  desde: f.desde || undefined,
  hasta: f.hasta || undefined,
  ruta_id: f.rutaId || undefined,
})

// Las comisiones se liquidan por mes (YYYY-MM): se derivan del rango de fechas elegido.
const periodos = (f: FiltroReportes) => ({
  periodo_desde: f.desde ? f.desde.slice(0, 7) : undefined,
  periodo_hasta: f.hasta ? f.hasta.slice(0, 7) : undefined,
})

export const obtenerRotacion = (f: FiltroReportes) =>
  httpClient
    .get<RotacionReporte>('/reports/inventory-turnover', { params: rango(f) })
    .then((r) => r.data)

export const obtenerVentasVsProyeccion = (f: FiltroReportes) =>
  httpClient
    .get<VentasProyeccionReporte>('/reports/sales-vs-forecast', { params: rango(f) })
    .then((r) => r.data)

export const obtenerComisiones = (f: FiltroReportes) =>
  httpClient
    .get<ComisionReporte>('/reports/commissions', {
      params: { ...periodos(f), ruta_id: f.rutaId || undefined },
    })
    .then((r) => r.data)

export type FormatoExport = 'xlsx' | 'csv'

/** Descarga el consolidado y lo entrega al navegador con el nombre que indica el servidor. */
export async function descargarConsolidado(f: FiltroReportes, formato: FormatoExport): Promise<void> {
  const r = await httpClient.get<Blob>('/reports/export', {
    params: { tipo: 'consolidado', formato, ...rango(f), ...periodos(f) },
    responseType: 'blob',
  })
  const cabecera = String(r.headers['content-disposition'] ?? '')
  const nombre = /filename="?([^";]+)"?/.exec(cabecera)?.[1] ?? `reporte_consolidado.${formato}`
  const url = URL.createObjectURL(r.data)
  const enlace = Object.assign(document.createElement('a'), { href: url, download: nombre })
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}
