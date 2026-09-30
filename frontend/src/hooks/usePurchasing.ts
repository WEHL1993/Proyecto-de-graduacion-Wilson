import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../services/purchasingApi'
import type { EstadoPedido, PedidoCreate } from '../types'

export const useSugerencias = (horizonteDias: number, habilitado: boolean) =>
  useQuery({
    queryKey: ['compras-sugerencias', horizonteDias],
    enabled: habilitado,
    retry: false,
    queryFn: () => api.obtenerSugerencias(horizonteDias),
  })

export const usePedidos = (estado?: EstadoPedido) =>
  useQuery({
    queryKey: ['compras-pedidos', estado ?? 'todos'],
    retry: false,
    refetchInterval: 60_000,
    queryFn: () => api.listarPedidos(estado),
  })

/** Toda mutación de un pedido invalida pedidos, sugerencias (el stock cambia al recibir) e inventario. */
function useInvalidar() {
  const cliente = useQueryClient()
  return () => {
    for (const k of ['compras-pedidos', 'compras-sugerencias', 'inventario-existencias', 'inventario-kardex'])
      void cliente.invalidateQueries({ queryKey: [k] })
  }
}

export function usePedidoActions() {
  const invalidar = useInvalidar()
  const opciones = { onSuccess: invalidar }
  return {
    crear: useMutation({ mutationFn: (s: PedidoCreate) => api.crearPedido(s), ...opciones }),
    enviar: useMutation({ mutationFn: (id: string) => api.enviarPedido(id), ...opciones }),
    cancelar: useMutation({ mutationFn: (id: string) => api.cancelarPedido(id), ...opciones }),
    confirmar: useMutation({
      mutationFn: (a: { id: string; fecha: string }) => api.confirmarPedido(a.id, a.fecha),
      ...opciones,
    }),
    recibir: useMutation({ mutationFn: (id: string) => api.recibirPedido(id), ...opciones }),
  }
}
