import type { AlertList, RouteItem } from '../types'
import { httpClient } from './httpClient'

export const listarRutas = () => httpClient.get<RouteItem[]>('/catalog/routes').then((r) => r.data)

export const listarAlertas = () =>
  httpClient
    .get<AlertList>('/alerts', { params: { estado: 'abierta', limit: 10 } })
    .then((r) => r.data)
