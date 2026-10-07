import type {
  EmpleadoCreate,
  EmpleadoOut,
  EmpleadoPage,
  EmpleadoUpdate,
  EquipoReemplazo,
  EquipoRutaOut,
  RutaAdminOut,
  RutaCreate,
  RutaDesalineada,
  RutaEquipoIncompleto,
  RutaUpdate,
} from '../types'
import { httpClient } from './httpClient'

// ---------------------------------------------------------------- rutas y equipos (M02)
export const listarRutasAdmin = () =>
  httpClient.get<RutaAdminOut[]>('/catalog/routes/admin').then((r) => r.data)

export const crearRuta = (datos: RutaCreate) =>
  httpClient.post<RutaAdminOut>('/catalog/routes', datos).then((r) => r.data)

export const actualizarRuta = (id: string, datos: RutaUpdate) =>
  httpClient.patch<RutaAdminOut>(`/catalog/routes/${id}`, datos).then((r) => r.data)

export const desactivarRuta = (id: string) =>
  httpClient.post<RutaAdminOut>(`/catalog/routes/${id}/deactivate`).then((r) => r.data)

export const activarRuta = (id: string) =>
  httpClient.post<RutaAdminOut>(`/catalog/routes/${id}/activate`).then((r) => r.data)

export const obtenerRuta = (id: string) =>
  httpClient.get<RutaAdminOut>(`/catalog/routes/${id}`).then((r) => r.data)

export const obtenerEquipo = (rutaId: string) =>
  httpClient.get<EquipoRutaOut>(`/catalog/routes/${rutaId}/team`).then((r) => r.data)

export const reemplazarEquipo = (rutaId: string, datos: EquipoReemplazo) =>
  httpClient.put<EquipoRutaOut>(`/catalog/routes/${rutaId}/team`, datos).then((r) => r.data)

export const equiposIncompletos = () =>
  httpClient.get<RutaEquipoIncompleto[]>('/catalog/teams/incomplete').then((r) => r.data)

export const rutasDesalineadas = () =>
  httpClient.get<RutaDesalineada[]>('/catalog/teams/misaligned').then((r) => r.data)

// ---------------------------------------------------------------- empleados
export interface FiltroEmpleados {
  q?: string
  /** `true` = activos, `false` = dados de baja (baja lógica). */
  activo: boolean
  limit?: number
  offset?: number
}

export const listarEmpleados = (f: FiltroEmpleados) =>
  httpClient
    .get<EmpleadoPage>('/employees', {
      params: { q: f.q || undefined, activo: f.activo, limit: f.limit ?? 50, offset: f.offset ?? 0 },
    })
    .then((r) => r.data)

export const crearEmpleado = (datos: EmpleadoCreate) =>
  httpClient.post<EmpleadoOut>('/employees', datos).then((r) => r.data)

export const actualizarEmpleado = (id: string, datos: EmpleadoUpdate) =>
  httpClient.patch<EmpleadoOut>(`/employees/${id}`, datos).then((r) => r.data)

export const darDeBajaEmpleado = (id: string) =>
  httpClient.delete(`/employees/${id}`).then(() => undefined)

export const reactivarEmpleado = (id: string) =>
  httpClient.post<EmpleadoOut>(`/employees/${id}/reactivate`).then((r) => r.data)
