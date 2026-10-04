import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import * as api from '../services/etlApi'
import type { OpcionesCarga } from '../services/etlApi'
import type { EtlConfig } from '../types'

export const TAMANO_PAGINA_LOTES = 10

export const useLotes = (pagina: number) =>
  useQuery({
    queryKey: ['etl-lotes', pagina],
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: () => api.listarLotes(TAMANO_PAGINA_LOTES, pagina * TAMANO_PAGINA_LOTES),
  })

/** Sube un `.xlsx` exponiendo el progreso de envío (0-100). Refresca el historial y las alertas. */
export function useSubirExcel() {
  const cliente = useQueryClient()
  const [progreso, setProgreso] = useState(0)
  const mutacion = useMutation({
    mutationFn: (a: { archivo: File; opciones: OpcionesCarga }) => {
      setProgreso(0)
      return api.subirExcel(a.archivo, a.opciones, setProgreso)
    },
    // También un rechazo (422) crea un lote y puede abrir una alerta `etl_error`.
    onSettled: () => {
      void cliente.invalidateQueries({ queryKey: ['etl-lotes'] })
      void cliente.invalidateQueries({ queryKey: ['alertas'] })
    },
  })
  return { ...mutacion, progreso }
}

/** Política de datos (ADR-14): ¿el arranque sigue abierto? ¿qué fuente usa el reentrenamiento? */
export const useEtlConfig = () =>
  useQuery({ queryKey: ['etl-config'], retry: false, queryFn: api.obtenerConfigEtl })

export function useGuardarEtlConfig() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (config: EtlConfig) => api.guardarConfigEtl(config),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ['etl-config'] }),
  })
}
