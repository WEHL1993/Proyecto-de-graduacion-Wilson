import { useQuery } from '@tanstack/react-query'
import * as api from '../services/inventoryApi'
import type { FiltroKardex } from '../services/inventoryApi'

export const useExistencias = () =>
  useQuery({ queryKey: ['inventario-existencias'], retry: false, queryFn: () => api.listarExistencias() })

export const useKardex = (filtro: FiltroKardex) =>
  useQuery({
    queryKey: ['inventario-kardex', filtro],
    retry: false,
    placeholderData: (previo) => previo,
    queryFn: () => api.listarKardex(filtro),
  })
