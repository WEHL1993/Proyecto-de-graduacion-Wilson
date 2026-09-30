import { useQuery } from '@tanstack/react-query'
import { predecirDemanda } from '../services/predictionsApi'
import { sumarDias } from '../utils/format'

/** Pronóstico de un producto en una ruta desde el día previo a la operación. */
export function useDemandForecast(opts: {
  productoId: string | null
  rutaId: string | null
  fechaOperacion: string
  horizonte: number
  habilitado: boolean
}) {
  const { productoId, rutaId, fechaOperacion, horizonte, habilitado } = opts
  return useQuery({
    queryKey: ['demanda', productoId, rutaId, fechaOperacion, horizonte],
    enabled: habilitado && Boolean(productoId && rutaId),
    retry: false,
    queryFn: () =>
      predecirDemanda({
        producto_ids: [productoId!],
        ruta_id: rutaId!,
        fecha_base: sumarDias(fechaOperacion, -1),
        horizonte_dias: horizonte,
        incluir_intervalo: true,
        persistir: false,
      }),
  })
}
