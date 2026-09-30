import { useQuery } from '@tanstack/react-query'
import * as api from '../services/reportsApi'
import type { FiltroReportes } from '../services/reportsApi'

const consulta = { retry: false, staleTime: 60_000 } as const

export const useRotacion = (f: FiltroReportes) =>
  useQuery({ queryKey: ['reporte-rotacion', f], queryFn: () => api.obtenerRotacion(f), ...consulta })

export const useVentasVsProyeccion = (f: FiltroReportes) =>
  useQuery({ queryKey: ['reporte-ventas', f], queryFn: () => api.obtenerVentasVsProyeccion(f), ...consulta })

export const useComisiones = (f: FiltroReportes) =>
  useQuery({ queryKey: ['reporte-comisiones', f], queryFn: () => api.obtenerComisiones(f), ...consulta })
