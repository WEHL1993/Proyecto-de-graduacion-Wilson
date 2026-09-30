import type {
  JobStatus,
  MetricsResponse,
  MlConfig,
  ModeloResumen,
  RetrainRequest,
  RetrainResponse,
} from '../types'
import { httpClient } from './httpClient'

export const obtenerMetricas = (desde: string, hasta: string) =>
  httpClient.get<MetricsResponse>('/ml/metrics', { params: { desde, hasta } }).then((r) => r.data)

export const listarModelos = () =>
  httpClient.get<{ modelos: ModeloResumen[] }>('/ml/models').then((r) => r.data.modelos)

export const reentrenar = (solicitud: RetrainRequest) =>
  httpClient.post<RetrainResponse>('/ml/models/retrain', solicitud).then((r) => r.data)

export const obtenerJob = (jobId: string) =>
  httpClient.get<JobStatus>(`/ml/jobs/${jobId}`).then((r) => r.data)

export const obtenerConfig = () => httpClient.get<MlConfig>('/ml/config').then((r) => r.data)

export const guardarConfig = (config: MlConfig) =>
  httpClient.put<MlConfig>('/ml/config', config).then((r) => r.data)
