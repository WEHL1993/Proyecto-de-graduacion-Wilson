// Espejo de la matriz RBAC 1.4 de la especificación: qué permiso(s) habilitan cada vista.
// El servidor sigue siendo la autoridad (403); esto solo evita mostrar lo que no se puede usar.
export const PERMISOS_VISTA = {
  dashboard: ['carga_ruta:generar', 'carga_ruta:aprobar'],
  monitoreo: ['ml:metricas:leer'],
  // Compras gestiona, Proveedor confirma, Bodega recibe.
  compras: ['pedido_proveedor:gestionar', 'pedido_proveedor:confirmar', 'inventario:ajustar'],
  inventario: ['inventario:leer'],
  etl: ['etl:cargar'],
  reportes: ['reportes:leer'],
  usuarios: ['usuarios:gestionar'],
} as const

export type Vista = keyof typeof PERMISOS_VISTA
