import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { listarCategorias, listarProveedores } from '../services/catalogApi'
import * as inventario from '../services/inventoryApi'
import * as api from '../services/productsApi'
import type { FiltroProductos } from '../services/productsApi'
import type { AjusteRequest, ProductoCreate, ProductoUpdate } from '../types'

export const useProductos = (filtro: FiltroProductos) =>
  useQuery({
    queryKey: ['productos', filtro],
    retry: false,
    placeholderData: (previo) => previo,
    queryFn: () => api.listarProductos(filtro),
  })

export const useCategorias = () =>
  useQuery({ queryKey: ['categorias'], staleTime: 5 * 60_000, retry: false, queryFn: listarCategorias })

export const useProveedores = () =>
  useQuery({ queryKey: ['proveedores'], staleTime: 5 * 60_000, retry: false, queryFn: listarProveedores })

/** Tras cualquier mutación se refrescan catálogo, existencias, kardex y alertas (stock bajo). */
const refrescar = (cliente: QueryClient) => {
  for (const clave of ['productos', 'inventario-existencias', 'inventario-kardex', 'alertas'])
    void cliente.invalidateQueries({ queryKey: [clave] })
}

export function useProductoActions() {
  const cliente = useQueryClient()
  const opciones = { onSuccess: () => refrescar(cliente) }
  return {
    crear: useMutation({ mutationFn: (d: ProductoCreate) => api.crearProducto(d), ...opciones }),
    actualizar: useMutation({
      mutationFn: (a: { id: string; datos: ProductoUpdate }) => api.actualizarProducto(a.id, a.datos),
      ...opciones,
    }),
    darDeBaja: useMutation({ mutationFn: (id: string) => api.darDeBajaProducto(id), ...opciones }),
    reactivar: useMutation({ mutationFn: (id: string) => api.reactivarProducto(id), ...opciones }),
    ajustar: useMutation({ mutationFn: (d: AjusteRequest) => inventario.ajustarStock(d), ...opciones }),
  }
}
