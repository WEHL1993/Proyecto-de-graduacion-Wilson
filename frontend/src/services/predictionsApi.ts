import type { DemandRequest, DemandResponse } from '../types'
import { httpClient } from './httpClient'

export const predecirDemanda = (solicitud: DemandRequest) =>
  httpClient.post<DemandResponse>('/predictions/demand', solicitud).then((r) => r.data)
