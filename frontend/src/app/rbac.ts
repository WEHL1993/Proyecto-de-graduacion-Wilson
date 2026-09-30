// Espejo de la matriz RBAC 1.4 de la especificación: qué permiso(s) habilitan cada vista.
// El servidor sigue siendo la autoridad (403); esto solo evita mostrar lo que no se puede usar.
export const PERMISOS_VISTA = {
  dashboard: ['carga_ruta:generar', 'carga_ruta:aprobar'],
  monitoreo: ['ml:metricas:leer'],
} as const

export type Vista = keyof typeof PERMISOS_VISTA
