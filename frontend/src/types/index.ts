// Tipos derivados del contrato: `npm run gen:api` regenera `openapi.d.ts` desde docs/architecture/openapi.yaml.
import type { components } from './openapi'

type S = components['schemas']

export type TokenResponse = S['TokenResponse']
export type LoadPlanRequest = S['LoadPlanRequest']
export type LoadPlanResponse = S['LoadPlanResponse']
export type LoadPlanItem = S['LoadPlanItem']
export type DemandRequest = S['DemandRequest']
export type DemandResponse = S['DemandResponse']
export type MetricsResponse = S['MetricsResponse']
export type MetricPoint = S['MetricPoint']
export type PeorProducto = S['PeorProducto']
export type RetrainRequest = S['RetrainRequest']
export type RetrainResponse = S['RetrainResponse']
export type JobStatus = S['JobStatus']
export type ModeloResumen = S['ModeloResumen']
export type MlConfig = S['MlConfig']
export type AlertList = S['AlertList']
export type RouteItem = S['RouteItem']

export type Algoritmo = RetrainRequest['algoritmos'][number]
export type EstadoCarga = LoadPlanResponse['estado']

export interface ApiError {
  codigo: string
  mensaje: string
  detalle?: Record<string, unknown>
}
