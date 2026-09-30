import type { LoadPlanRequest, LoadPlanResponse } from '../types'
import { httpClient } from './httpClient'

export const obtenerCargaVigente = (rutaId: string, fecha: string) =>
  httpClient
    .get<LoadPlanResponse>('/routes/load-plans', {
      params: { ruta_id: rutaId, fecha_operacion: fecha },
    })
    .then((r) => r.data)

export const gestionarCarga = (solicitud: LoadPlanRequest) =>
  httpClient.post<LoadPlanResponse>('/routes/load-plans', solicitud).then((r) => r.data)
