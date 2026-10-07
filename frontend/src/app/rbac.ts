// Espejo de la matriz RBAC 1.4 de la especificación: qué permiso(s) habilitan cada vista.
// El servidor sigue siendo la autoridad (403); esto solo evita mostrar lo que no se puede usar.
export const PERMISOS_VISTA = {
  dashboard: ['carga_ruta:generar', 'carga_ruta:aprobar'],
  monitoreo: ['ml:metricas:leer'],
  // EncargadoCompras gestiona, Proveedor confirma, EncargadoBodega recibe.
  compras: ['pedido_proveedor:gestionar', 'pedido_proveedor:confirmar', 'inventario:ajustar'],
  inventario: ['inventario:leer'],
  // ADR-16: quien consulta inventario ve el catálogo; las acciones se habilitan por `productos:*`.
  productos: ['inventario:leer'],
  etl: ['etl:cargar'],
  reportes: ['reportes:leer'],
  usuarios: ['usuarios:gestionar'],
  // ADR-14: Administrador y Liquidador liquidan (registrar); Administrador, Liquidador y Gerente consultan el historial.
  liquidacion: ['liquidaciones:registrar'],
  liquidaciones: ['liquidaciones:leer'],
  // Política de datos (cierre del arranque ETL): solo Administrador.
  etlConfig: ['etl:configurar'],
  // M02 (ADR-18): rutas, empleados y equipos de ruta. Escribir exige además `catalogos:gestionar`.
  catalogos: ['catalogos:leer'],
} as const

export type Vista = keyof typeof PERMISOS_VISTA
