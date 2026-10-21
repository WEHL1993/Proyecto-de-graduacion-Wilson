# Recepción de mercadería

La ruta `/recepcion` y su entrada en el menú requieren `inventario:ajustar`.
Desde Compras, «Registrar recepción física» abre esta vista con el pedido seleccionado.
El origen de la mercadería es la planta central; no se selecciona un proveedor.

El formulario exige el encabezado de la factura electrónica (FEL) de planta central:

- Obligatorios: `serie`, `numero`, `numero_autorizacion` (UUID) y `fecha_emision` (fecha).
- Opcionales: `condicion_pago`, `serie_admin` y `numero_admin`; estos dos últimos son
  la referencia interna (ejemplo: FEL14 / 77058).

La serie se recorta y convierte a mayúsculas; el número se conserva como texto de
dígitos para no perder ceros iniciales. El UUID se almacena como UUID de PostgreSQL,
por lo que sus mayúsculas/minúsculas no alteran su identidad. La UI valida su formato
básico con guiones. No se valida NIT ni se calcula fecha de vencimiento.

Con pedido se incluyen todos sus productos,
con cantidad pedida, cantidad realmente recibida y observación. Cero documenta una
falta y no genera un movimiento. Sin pedido se agregan productos activos y sus
cantidades deben ser positivas. Debe existir al menos una cantidad positiva.

`POST /api/v1/purchasing/receipts` guarda el documento y sus líneas en
`recepciones_mercaderia`. Cada producto recibido genera una ENTRADA con
`referencia_tipo=recepcion`, el UUID de la recepción y
`FEL {serie}-{numero} / {numero_autorizacion}` en `motivo`.
El caso de uso confirma documento, existencias, kardex y estado en un solo commit;
el servicio de inventario continúa haciendo únicamente flush.

Si todas las cantidades coinciden, el pedido queda `recibido`. Cualquier diferencia,
incluido un excedente, lo deja `recibido_parcial`. Ambos estados cierran la recepción:
no se habilitan entregas acumulativas sobre pedidos parciales. El bloqueo de la
cabecera evita recibir dos veces el mismo pedido. Sin pedido no cambia ningún pedido.

`GET /api/v1/purchasing/receipt-products` permite cargar el catálogo con el mismo
permiso de recepción, sin exigir permisos adicionales. La vista recorre todas las
páginas de productos y pedidos confirmados.

El endpoint anterior `POST /purchasing/orders/{id}/receive` conserva su comportamiento
para compatibilidad; la interfaz usa el nuevo flujo documentado.

La migración `0009` depende de `0008`, amplía el estado del pedido a varchar(20),
actualiza los CHECK y crea la tabla de recepciones. Su reversión rechaza eliminar
recepciones existentes para evitar perder documentos.

La nueva migración `0010` depende de `0009`; la `0009` no se modifica. Añade los
campos FEL y dos restricciones UNIQUE: `numero_autorizacion` y `(serie, numero)`.
Las recepciones históricas conservan `documento_referencia` y los campos FEL nulos;
no se inventan autorizaciones ni fechas para ellas. La obligatoriedad de los campos
FEL se aplica a todas las solicitudes nuevas mediante los schemas de la API.

Las facturas repetidas responden HTTP **409** con `codigo=FACTURA_DUPLICADA` y un
mensaje en español. La UI muestra el mensaje y conserva lo capturado. La consulta
previa permite detectar también un reintento de un pedido ya recibido; las
restricciones de BD cubren carreras concurrentes. Su conflicto se traduce al mismo
409 mediante un savepoint antes de registrar entradas. El stock no se duplica.

Validación desde la raíz, en PowerShell:

```powershell
$env:DATABASE_URL='postgresql+psycopg2://ds_user:ds_password@localhost:55432/ds_predictive'
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
$pruebasTemporal = Join-Path (Get-Location) ('backend/.pytest_cache/recepcion-' + [guid]::NewGuid().ToString('N'))
backend/.venv/Scripts/python.exe -m pytest backend/tests -q --basetemp $pruebasTemporal
npm --prefix frontend test
npm --prefix frontend run build
```

Las pruebas nuevas de recepción exigen explícitamente el puerto 55432.
