# Cambios M01 · Seguridad y usuarios (Entregable 3)

## 1. Nombre en tesis → nombre en sistema

| Actor en la tesis | Nombre anterior en el sistema | Nombre en el sistema (`roles.nombre`) |
|---|---|---|
| Administrador | Admin | `Administrador` |
| Encargado de inventario | Inventario | `EncargadoInventario` |
| Encargado de ventas | Ventas | `EncargadoVentas` |
| Encargado de bodega | Bodega | `EncargadoBodega` |
| Encargado de compras | Compras | `EncargadoCompras` |
| Gerente o encargado comercial | Gerente | `Gerente` |
| Proveedor | Proveedor | `Proveedor` |
| *(rol operativo añadido en el diseño)* | Liquidador | `Liquidador` |

Los códigos de permiso (`recurso:accion`) no cambian. El renombrado se aplica con la migración
`0005`, que conserva los identificadores de rol: ningún usuario pierde acceso.

## 2. Rol Liquidador

**Descripción:** persona responsable de registrar y cerrar la liquidación diaria por ruta y vendedor.

| Permiso | Alcance |
|---|---|
| `liquidaciones:registrar` | Registro y edición de borradores de la liquidación diaria |
| `liquidaciones:cerrar` | Cierre de la liquidación diaria (alimenta el modelo predictivo) |
| `liquidaciones:leer` | Consulta del historial de liquidaciones y su cuadre de caja |

No posee `liquidaciones:corregir` (corrección y anulación, exclusivas del Administrador), ni permisos
para aprobar cargas de ruta, gestionar compras o administrar usuarios; el servidor responde 403.
En la interfaz accede únicamente a «Liquidación Diaria» y «Historial de Liquidaciones».

## 3. Matriz rol → permisos (resumen)

| Rol | Permisos |
|---|---|
| Administrador | Todos |
| EncargadoInventario | `etl:cargar`, `prediccion:consultar`, `inventario:leer`, `inventario:ajustar`, `productos:crear/editar/eliminar`, `alertas:leer` |
| EncargadoVentas | `etl:cargar`, `prediccion:consultar`, `carga_ruta:generar`, `carga_ruta:aprobar`, `inventario:leer`, `alertas:leer` |
| EncargadoBodega | `carga_ruta:despachar`, `inventario:leer`, `inventario:ajustar`, `alertas:leer` |
| EncargadoCompras | `prediccion:consultar`, `inventario:leer`, `pedido_proveedor:gestionar`, `alertas:leer` |
| Gerente | `reportes:leer`, `prediccion:consultar`, `carga_ruta:aprobar`, `inventario:leer`, `ml:metricas:leer`, `ml:reentrenar`, `alertas:leer`, `liquidaciones:leer` |
| Proveedor | `pedido_proveedor:confirmar` (solo sus propios pedidos) |
| Liquidador | `liquidaciones:registrar`, `liquidaciones:cerrar`, `liquidaciones:leer` |
