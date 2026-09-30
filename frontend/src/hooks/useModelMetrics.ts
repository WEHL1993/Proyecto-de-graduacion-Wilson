import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import * as api from '../services/mlApi'
import type { MlConfig, RetrainRequest } from '../types'
import { esStatus } from '../utils/errors'
import { hoyISO, sumarDias } from '../utils/format'

export function useModelMetrics(dias: number, habilitado = true) {
  const hasta = hoyISO()
  return useQuery({
    queryKey: ['ml-metricas', dias],
    enabled: habilitado,
    retry: false,
    refetchInterval: 60_000,
    queryFn: () => api.obtenerMetricas(sumarDias(hasta, -dias), hasta),
  })
}

export const useModelos = () =>
  useQuery({ queryKey: ['ml-modelos'], queryFn: api.listarModelos, retry: false })

export const useMlConfig = () =>
  useQuery({ queryKey: ['ml-config'], queryFn: api.obtenerConfig, retry: false })

export function useGuardarConfig() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (c: MlConfig) => api.guardarConfig(c),
    onSuccess: () => {
      void cliente.invalidateQueries({ queryKey: ['ml-config'] })
      void cliente.invalidateQueries({ queryKey: ['ml-metricas'] })
    },
  })
}

/** Dispara el reentrenamiento y sondea el job hasta que termine (progreso del wireframe 2b). */
export function useRetrain() {
  const cliente = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)

  const disparo = useMutation({
    mutationFn: (s: RetrainRequest) => api.reentrenar(s),
    onSuccess: (r) => setJobId(r.job_id),
  })

  const job = useQuery({
    queryKey: ['ml-job', jobId],
    enabled: jobId !== null,
    queryFn: () => api.obtenerJob(jobId!),
    retry: false,
    refetchInterval: (q) => {
      const estado = q.state.data?.estado
      return estado === 'completado' || estado === 'fallido' ? false : 3000
    },
  })

  const terminado = job.data?.estado === 'completado' || job.data?.estado === 'fallido'
  useEffect(() => {
    if (terminado) {
      void cliente.invalidateQueries({ queryKey: ['ml-metricas'] })
      void cliente.invalidateQueries({ queryKey: ['ml-modelos'] })
      void cliente.invalidateQueries({ queryKey: ['alertas'] })
    }
  }, [terminado, cliente])

  return { disparo, job, jobId, olvidar: () => setJobId(null) }
}

export const sinModeloProductivo = (e: unknown): boolean => esStatus(e, 400)
