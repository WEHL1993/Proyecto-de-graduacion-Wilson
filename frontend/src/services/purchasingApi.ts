import type { EstadoPedido, PedidoCreate, PedidoOut, PedidoPage, SugerenciasResponse } from '../types'
import { httpClient } from './httpClient'

export const obtenerSugerencias = (horizonteDias: number) =>
  httpClient
    .get<SugerenciasResponse>('/purchasing/suggestions', { params: { horizonte_dias: horizonteDias } })
    .then((r) => r.data)

export const listarPedidos = (estado?: EstadoPedido) =>
  httpClient
    .get<PedidoPage>('/purchasing/orders', { params: { estado, limit: 100 } })
    .then((r) => r.data)

export const crearPedido = (solicitud: PedidoCreate) =>
  httpClient.post<PedidoOut>('/purchasing/orders', solicitud).then((r) => r.data)

export const enviarPedido = (id: string) =>
  httpClient.post<PedidoOut>(`/purchasing/orders/${id}/send`).then((r) => r.data)

export const cancelarPedido = (id: string) =>
  httpClient.post<PedidoOut>(`/purchasing/orders/${id}/cancel`).then((r) => r.data)

export const confirmarPedido = (id: string, fechaEsperada: string) =>
  httpClient
    .patch<PedidoOut>(`/purchasing/orders/${id}/confirm`, { fecha_esperada: fechaEsperada })
    .then((r) => r.data)

export const recibirPedido = (id: string) =>
  httpClient.post<PedidoOut>(`/purchasing/orders/${id}/receive`).then((r) => r.data)
