import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../services/loadPlansApi'
import type { LoadPlanRequest, LoadPlanResponse } from '../types'
import { esStatus } from '../utils/errors'

/** Carga vigente de una ruta y fecha; `null` si aún no se ha generado (404). */
export function useLoadPlan(rutaId: string | null, fecha: string | null) {
  return useQuery({
    queryKey: ['plan', rutaId, fecha],
    enabled: Boolean(rutaId && fecha),
    retry: false,
    queryFn: async (): Promise<LoadPlanResponse | null> => {
      try {
        return await api.obtenerCargaVigente(rutaId!, fecha!)
      } catch (e) {
        if (esStatus(e, 404)) return null
        throw e
      }
    },
  })
}

export function useLoadPlanActions(rutaId: string | null, fecha: string | null) {
  const cliente = useQueryClient()
  const clave = ['plan', rutaId, fecha]
  const mutacion = useMutation({
    mutationFn: (s: LoadPlanRequest) => api.gestionarCarga(s),
    onSuccess: (plan) => {
      // Un plan rechazado libera el cupo: el "vigente" pasa a ser ninguno.
      cliente.setQueryData(clave, plan.estado === 'rechazada' ? null : plan)
      void cliente.invalidateQueries({ queryKey: ['alertas'] })
    },
  })
  /** Recalcular = rechazar el borrador vigente y generar uno nuevo con el stock de hoy. */
  const recalcular = useMutation({
    mutationFn: async (plan: LoadPlanResponse) => {
      await api.gestionarCarga({
        accion: 'rechazar',
        carga_id: plan.carga_id,
        motivo_rechazo: 'Recalculado desde el dashboard',
      })
      return api.gestionarCarga({ accion: 'generar', ruta_id: plan.ruta_id, fecha_operacion: plan.fecha_operacion })
    },
    onSuccess: (plan) => {
      cliente.setQueryData(clave, plan)
      void cliente.invalidateQueries({ queryKey: ['alertas'] })
    },
  })
  return { mutacion, recalcular }
}
