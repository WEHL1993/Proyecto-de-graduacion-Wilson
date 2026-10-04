import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../services/liquidacionesApi'
import type { FiltroLiquidaciones } from '../services/liquidacionesApi'
import type { LiquidacionConfig, LiquidacionRequest } from '../types'

export const usePrecarga = (fecha: string, rutaId: string) =>
  useQuery({
    queryKey: ['liquidaciones', 'precarga', fecha, rutaId],
    enabled: Boolean(fecha && rutaId),
    retry: false,
    queryFn: () => api.precargar(fecha, rutaId),
  })

export const useListadoLiquidaciones = (filtro: FiltroLiquidaciones) =>
  useQuery({
    queryKey: ['liquidaciones', 'listado', filtro],
    placeholderData: keepPreviousData,
    retry: false,
    queryFn: () => api.listarLiquidaciones(filtro),
  })

export const useLiquidacionDetalle = (id: string | null) =>
  useQuery({
    queryKey: ['liquidaciones', 'detalle', id],
    enabled: Boolean(id),
    retry: false,
    queryFn: () => api.obtenerLiquidacion(id as string),
  })

export const useConfigLiquidacion = (habilitado = true) =>
  useQuery({
    queryKey: ['liquidaciones', 'config'],
    enabled: habilitado,
    retry: false,
    queryFn: api.obtenerConfigLiquidacion,
  })

export function useGuardarConfigLiquidacion() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (c: LiquidacionConfig) => api.guardarConfigLiquidacion(c),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ['liquidaciones', 'config'] }),
  })
}

const DEPENDIENTES = [
  'liquidaciones',
  'plan',
  'ml-metricas',
  'ml-modelos',
  'alertas',
  'reporte-rotacion',
  'reporte-ventas',
  'reporte-comisiones',
]

/** Una liquidación cerrada alimenta plan de carga, monitoreo, alertas y reportes: se refrescan. */
function useInvalidarDependientes() {
  const cliente = useQueryClient()
  return () => {
    for (const k of DEPENDIENTES) void cliente.invalidateQueries({ queryKey: [k] })
  }
}

export function useGuardarLiquidacion() {
  const invalidar = useInvalidarDependientes()
  return useMutation({ mutationFn: (c: LiquidacionRequest) => api.guardarLiquidacion(c), onSuccess: invalidar })
}

export function useCerrarLiquidacion() {
  const invalidar = useInvalidarDependientes()
  return useMutation({ mutationFn: (id: string) => api.cerrarLiquidacion(id), onSuccess: invalidar })
}

export function useCorregirLiquidacion() {
  const invalidar = useInvalidarDependientes()
  return useMutation({
    mutationFn: (a: { id: string; cuerpo: LiquidacionRequest; motivo: string }) =>
      api.corregirLiquidacion(a.id, a.cuerpo, a.motivo),
    onSuccess: invalidar,
  })
}

export function useAnularLiquidacion() {
  const invalidar = useInvalidarDependientes()
  return useMutation({
    mutationFn: (a: { id: string; motivo: string }) => api.anularLiquidacion(a.id, a.motivo),
    onSuccess: invalidar,
  })
}
