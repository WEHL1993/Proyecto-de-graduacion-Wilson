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


export const registrarRecepcion = (solicitud: import('../types').RecepcionCreate) =>
  httpClient.post<import('../types').RecepcionOut>('/purchasing/receipts', solicitud).then((r) => r.data)

/** Carga todas las p?ginas para no ocultar pedidos o productos fuera de la primera. */
export async function pedidosPendientes() {
  const items: PedidoOut[] = []
  let total = 0
  do {
    const { data } = await httpClient.get<PedidoPage>('/purchasing/orders', {
      params: { estado: 'confirmado', limit: 100, offset: items.length },
    })
    items.push(...data.items)
    total = data.total
    if (!data.items.length) break
  } while (items.length < total)
  return items
}

export async function productosRecepcion() {
  const items: import('../types').ProductoOut[] = []
  let total = 0
  do {
    const { data } = await httpClient.get<import('../types').ProductoPage>('/purchasing/receipt-products', {
      params: { limit: 200, offset: items.length },
    })
    items.push(...data.items)
    total = data.total
    if (!data.items.length) break
  } while (items.length < total)
  return items
}
