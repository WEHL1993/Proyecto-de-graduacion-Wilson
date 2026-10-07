import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import * as api from '../services/routesAdminApi'
import type { FiltroEmpleados } from '../services/routesAdminApi'
import type {
  EmpleadoCreate,
  EmpleadoUpdate,
  EquipoReemplazo,
  RutaCreate,
  RutaUpdate,
} from '../types'

export const useRutasAdmin = () =>
  useQuery({ queryKey: ['rutas-admin'], retry: false, queryFn: api.listarRutasAdmin })

export const useRutaAdmin = (id: string) =>
  useQuery({ queryKey: ['rutas-admin', id], retry: false, queryFn: () => api.obtenerRuta(id) })

export const useEquipo = (rutaId: string) =>
  useQuery({ queryKey: ['equipo-ruta', rutaId], retry: false, queryFn: () => api.obtenerEquipo(rutaId) })

export const useEquiposIncompletos = () =>
  useQuery({ queryKey: ['equipos-informe', 'incompletos'], retry: false, queryFn: api.equiposIncompletos })

export const useRutasDesalineadas = () =>
  useQuery({ queryKey: ['equipos-informe', 'desalineadas'], retry: false, queryFn: api.rutasDesalineadas })

export const useEmpleados = (filtro: FiltroEmpleados) =>
  useQuery({
    queryKey: ['empleados', filtro],
    retry: false,
    placeholderData: (previo) => previo,
    queryFn: () => api.listarEmpleados(filtro),
  })

/** Tras cualquier cambio se refrescan rutas (admin y filtro público), equipos, informes y empleados. */
const refrescar = (cliente: QueryClient) => {
  for (const clave of ['rutas-admin', 'rutas', 'equipo-ruta', 'equipos-informe', 'empleados'])
    void cliente.invalidateQueries({ queryKey: [clave] })
}

export function useRutaActions() {
  const cliente = useQueryClient()
  const opciones = { onSuccess: () => refrescar(cliente) }
  return {
    crear: useMutation({ mutationFn: (d: RutaCreate) => api.crearRuta(d), ...opciones }),
    actualizar: useMutation({
      mutationFn: (a: { id: string; datos: RutaUpdate }) => api.actualizarRuta(a.id, a.datos),
      ...opciones,
    }),
    desactivar: useMutation({ mutationFn: (id: string) => api.desactivarRuta(id), ...opciones }),
    activar: useMutation({ mutationFn: (id: string) => api.activarRuta(id), ...opciones }),
    guardarEquipo: useMutation({
      mutationFn: (a: { rutaId: string; datos: EquipoReemplazo }) => api.reemplazarEquipo(a.rutaId, a.datos),
      ...opciones,
    }),
  }
}

export function useEmpleadoActions() {
  const cliente = useQueryClient()
  const opciones = { onSuccess: () => refrescar(cliente) }
  return {
    crear: useMutation({ mutationFn: (d: EmpleadoCreate) => api.crearEmpleado(d), ...opciones }),
    actualizar: useMutation({
      mutationFn: (a: { id: string; datos: EmpleadoUpdate }) => api.actualizarEmpleado(a.id, a.datos),
      ...opciones,
    }),
    darDeBaja: useMutation({ mutationFn: (id: string) => api.darDeBajaEmpleado(id), ...opciones }),
    reactivar: useMutation({ mutationFn: (id: string) => api.reactivarEmpleado(id), ...opciones }),
  }
}
