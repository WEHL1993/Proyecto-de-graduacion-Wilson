# Prompt: Módulo «Liquidación diaria de ventas» (unidades + dinero) como fuente de entrenamiento

> Copiar el bloque de la sección **Prompt** en una nueva sesión de Claude Code, en la raíz del proyecto.
> Reemplaza la versión anterior («Cierre diario», solo unidades).

## Contexto del hallazgo

- Al final del día, los vendedores entregan al admin lo vendido por presentación **y el dinero**
  (efectivo, transferencias, ventas a crédito/saldos, gastos de ruta). Hoy no existe ningún módulo que lo
  registre: la única entrada de ventas es `POST /etl/upload-excel` (permiso `etl:cargar`, vista
  `EtlUploadView`), pensada para histórico mensual en formato ancho.
- Los Excel reales ya traen la lógica de liquidación (`Carga NN`, `ventas NN`, `Efectivo NN`, `Saldo NN`
  por día y vendedor), pero el sistema solo ingiere ventas; **efectivo y saldos se pierden**.
- Consecuencias del vacío:
  - No hay captura diaria por ruta/vendedor/producto ni cuadre de caja.
  - `demanda_real` (spec: «NULL hasta cierre del día») nunca se llena sin subir un Excel; el job
    `evaluate_production` (ADR-12) y el reentrenamiento por degradación (ADR-08) dependen de ello.
  - No hay reconciliación cargado = vendido + devuelto + merma, ni se detectan faltantes de dinero.
- Destino natural de las ventas: `ventas_historicas` (`fecha_venta`, `producto_id`, `ruta_id`,
  `vendedor_id`, `cantidad`, `precio_unitario`, `monto_total`; única
  `uq_ventas_historicas_fecha_producto_ruta_vendedor`; FK `lote_id -> etl_lotes`). De ahí leen
  `training_service` y `feature_engineering`.

## Política de datos del modelo (decisión del negocio)

1. **Entrenamiento inicial**: con los Excel que la empresa ya posee (ETL existente, sin cambios de
   comportamiento). Esos datos son la línea base histórica.
2. **Operación continua**: los datos nuevos entran **solo** por la liquidación diaria. Los
   reentrenamientos posteriores se alimentan de lo liquidado, no de nuevas cargas de Excel.
3. Para que el modelo conserve rezagos/estacionalidad, la línea base Excel queda como historia
   congelada (`origen='excel_historico'`) y las liquidaciones se añaden con `origen='liquidacion'`.
   Los reentrenamientos usan base + liquidaciones, pero **ninguna carga de Excel nueva** puede
   alimentar el modelo una vez cerrado el arranque (ver `etl.carga_excel_habilitada`).

## Prompt

```text
Lee CLAUDE.md y docs/architecture/00-especificacion.md (1.4 RBAC, 3 ER, 4 OpenAPI, 5 QA,
6.3 orden de implementación, ADR-04/06/07/08/09/10/11/12/13) y luego implementa el módulo
«Liquidación diaria de ventas».

OBJETIVO
El admin liquida cada día, por ruta y vendedor: (a) unidades por presentación (cargado, vendido,
devuelto, merma) y (b) dinero (venta total, efectivo, transferencia, crédito, cobro de saldos
anteriores, gastos, efectivo entregado y diferencia). Al cerrar la liquidación:
1. Las ventas por presentación quedan en ventas_historicas (origen 'liquidacion') y son la fuente de
   los reentrenamientos posteriores al entrenamiento inicial con Excel.
2. Se rellena demanda_real de las predicciones de esa fecha/ruta/producto.
3. Se encola evaluate_production (ADR-12) sin entrenar dentro de la petición.
4. Se calcula el cuadre de caja y de unidades.

ANTES DE CODIFICAR
1. Revisa: services/etl_service.py, services/training_service.py, ml/feature_engineering.py,
   repositories/sales_repo.py, repositories/forecast_repo.py, domain/models/sales.py (EtlLote,
   VentaHistorica, Comision), domain/enums.py, services/monitoring_service.py,
   services/retraining_service.py, services/load_plan_service.py (cargas despachadas),
   services/report_service.py (comisiones/reportes leen ventas_historicas), api/v1/etl.py,
   core/rbac.py, frontend/src/app/rbac.ts y data/raw/ (hojas Efectivo NN / Saldo NN).
2. Redacta una ADR nueva (siguiente número libre tras ADR-13) en la especificación con las decisiones
   de abajo, actualiza el ER (sección 3) y la matriz RBAC (1.4). Ante ambigüedad prevalecen el
   contrato OpenAPI y el ER; toda desviación se documenta en la ADR.

MODELO DE DATOS (migraciones NUEVAS con `make revision m="..."`; nunca editar una aplicada; revisar a
mano; `alembic check` sin drift; probar upgrade/downgrade; importar en domain/models/__init__.py)
Convenciones sección 3.1: PK uuid gen_random_uuid(); timestamptz UTC; montos numeric(14,2); cantidades
numeric(12,2); estados varchar + CHECK con sql_in() desde domain/enums.py (nuevo enum
EstadoLiquidacion: borrador, cerrada, anulada; y MetodoPago si se usa).
- etl_lotes: añadir `origen` varchar + CHECK sql_in(OrigenDatos: excel_historico, liquidacion),
  server_default 'excel_historico' (los lotes existentes quedan como Excel). Un lote por liquidación
  cerrada, con checksum = hash determinista de (fecha, ruta_id, vendedor_id, líneas ordenadas).
- liquidaciones_diarias (cabecera): id, fecha, ruta_id, vendedor_id, estado, version (int, corrección),
  lote_id (nullable hasta cerrar), venta_total, total_efectivo, total_transferencia, total_credito,
  cobro_saldos_anteriores, gastos_ruta, efectivo_esperado (= total_efectivo + cobro_saldos -
  gastos_ruta), efectivo_entregado, diferencia_caja (= entregado - esperado), observaciones,
  creado_por, cerrado_en, anulado_en/motivo. Única parcial (fecha, ruta_id, vendedor_id) WHERE
  estado <> 'anulada'. CHECK: montos >= 0 y venta_total = efectivo + transferencia + crédito.
- liquidacion_detalles: liquidacion_id, producto_id, cantidad_cargada, cantidad_vendida,
  cantidad_devuelta, cantidad_merma, precio_unitario, monto_total, agotado (bool: se quedó sin
  producto antes de terminar la ruta → demanda censurada). Única (liquidacion_id, producto_id). CHECK:
  cantidades >= 0 y vendida + devuelta + merma <= cargada.
- saldos_clientes (cuentas por cobrar), opcional si los Excel tienen cliente: cliente, ruta, saldo,
  movimientos (venta a crédito +, cobro −) ligados a la liquidación. Si los datos no permiten
  identificar cliente, guarda solo el total por liquidación y documenta la limitación en la ADR.
- parametros_sistema: `etl.carga_excel_habilitada` (bool, true hasta el arranque) y
  `ml.fuente_reentrenamiento` ('excel_mas_liquidacion' por defecto tras el arranque).
- Auditoría: registrar en app.auditoria creación, corrección y anulación (usuario, antes/después).

REGLAS DE NEGOCIO
- Fecha no futura. Ruta y productos activos. Cantidades y montos >= 0. Producto no repetido en la
  liquidación. Al menos una línea con venta o cargada.
- precio_unitario por defecto = catálogo vigente (sobrescribible por línea). monto = cantidad vendida
  × precio (numeric(14,2)).
- Cuadre de unidades: cargada = vendida + devuelta + merma. Si no cuadra, 400 UNIDADES_NO_CUADRAN con
  el detalle por producto (el CHECK ya impide que la suma exceda lo cargado). Si hay carga
  despachada de esa ruta/fecha, precargar cantidad_cargada desde detalle_cargas (editable con
  justificación); si no hay carga, permitir con advertencia, nunca bloquear.
- Cuadre de dinero: venta_total debe igualar la suma de líneas y a efectivo+transferencia+crédito
  (400 MONTOS_NO_CUADRAN). La diferencia de caja NO bloquea: se registra y, si supera el umbral
  `liquidacion.umbral_diferencia_caja` (parametros_sistema), genera alerta `diferencia_caja`
  visible para Administrador y Gerente.
- Estados: borrador → cerrada (al cerrar se escribe en ventas_historicas) → anulada. Un borrador puede
  guardarse sin afectar el modelo. Cerrar es explícito (acción `cerrar`).
- Corrección de una liquidación cerrada: permitida (permiso aparte), incrementa `version`, hace UPSERT
  en ventas_historicas por la restricción única existente, recalcula demanda_real y vuelve a encolar
  evaluate_production. Anular: elimina/neutraliza las ventas_historicas del lote con auditoría y
  motivo obligatorio (409 LIQUIDACION_YA_ANULADA).
- Nunca despachar ni modificar stock automáticamente (ADR-06). Las devoluciones se muestran como
  «devolución esperada» para que el flujo de inventario las procese por su propio camino.
- Códigos de error en español: LIQUIDACION_DUPLICADA, VENTA_FECHA_FUTURA, PRODUCTO_DUPLICADO_EN_CIERRE,
  PRODUCTO_INACTIVO, UNIDADES_NO_CUADRAN, MONTOS_NO_CUADRAN, LIQUIDACION_NO_CERRADA,
  LIQUIDACION_YA_CERRADA, LIQUIDACION_YA_ANULADA.

INTEGRACIÓN CON EL MODELO (parte crítica)
- training_service / feature_engineering: leer ventas_historicas filtrando por origen según
  `ml.fuente_reentrenamiento`. El entrenamiento inicial sigue usando los Excel (scripts/train_model.py y
  POST /ml/train sin cambios de comportamiento). Los reentrenamientos por degradación (ADR-08) usan
  base Excel + liquidaciones; si faltan días en la serie liquidada, se aplica la regla de ADR-12
  (día sin fila = 0) solo dentro del rango efectivamente liquidado, y se reporta HISTORIAL_INSUFICIENTE
  si no hay ≥ 28 días por serie.
- Sesgo de demanda censurada: añade features opcionales derivadas de la liquidación (`agotado`,
  tasa de devolución, merma, día de la semana de cierre) y, si `agotado=true`, marca la observación
  como censurada: demanda_real = vendido es un piso, no la demanda total. Documenta en la ADR cómo
  la usa el entrenamiento (p. ej. peso menor o feature) y cómo evalúa evaluate_production.
- Puerta del ETL: `POST /etl/upload-excel` responde 409 EXCEL_DESHABILITADO cuando
  `etl.carga_excel_habilitada=false`. Añade `PUT` administrativo (parámetro de sistema) para cerrar el
  arranque, auditado. Los datos Excel ya cargados no se tocan.
- Trazabilidad: cada modelo en `modelos_ml` registra rango de fechas y conteo de filas por origen
  usadas en el entrenamiento (sin romper el esquema existente: usar JSONB de métricas/metadatos si ya
  existe, o migración nueva si no).
- Monitoreo (ADR-12): demanda_real llega ahora por la liquidación; evaluate_production sigue siendo la
  única que calcula MAE/RMSE/MAPE y degradación.

CAPAS (obligatorio: api -> services -> repositories -> domain)
- schemas/liquidacion.py: DTOs Pydantic v2: LiquidacionRequest{fecha, ruta_id, vendedor_id,
  lineas[{producto_id, cantidad_cargada, cantidad_vendida, cantidad_devuelta, cantidad_merma,
  precio_unitario?, agotado?}], pagos{efectivo, transferencia, credito, cobro_saldos, gastos,
  efectivo_entregado}, observaciones?}, LiquidacionResponse (totales, cuadres, diferencia_caja, lote_id,
  advertencias), ListadoLiquidaciones paginado.
- api/v1/liquidaciones.py (registrar en api/v1/router.py), sin reglas ni SQL:
  `POST /liquidaciones` (crea/actualiza borrador), `GET /liquidaciones/precarga?fecha=&ruta_id=`
  (carga despachada + liquidación existente), `GET /liquidaciones` (historial paginado, filtros
  fecha/ruta/vendedor/estado), `GET /liquidaciones/{id}`, `POST /liquidaciones/{id}/cerrar`,
  `POST /liquidaciones/{id}/corregir`, `POST /liquidaciones/{id}/anular`.
- services/liquidacion_service.py: validaciones, cuadres, cierre transaccional (lote + UPSERT en
  ventas_historicas + demanda_real + encolado del job + alertas + auditoría en UNA transacción).
- repositories/liquidacion_repo.py (+ sales_repo.py, forecast_repo.py, alert repo): únicas consultas
  SQLAlchemy, estilo Mapped[...].
- workers/: sin lógica nueva salvo que evaluate_production reciba la fecha como parámetro del job.
- RBAC (matriz 1.4, core/rbac.py, frontend/src/app/rbac.ts): `liquidaciones:registrar` (Administrador),
  `liquidaciones:cerrar` (Administrador), `liquidaciones:corregir` (Administrador; anular incluido),
  `liquidaciones:leer` (Administrador y Gerente). 401 sin sesión, 403 sin permiso; denegación auditada.
- `make openapi` y versionar docs/architecture/openapi.yaml en el mismo cambio; luego
  `npm run gen:api` en frontend.

FRONTEND
- Vista `frontend/src/views/LiquidacionDiariaView.tsx` en `/ventas/liquidacion`, protegida con
  PermissionGate + PERMISOS_VISTA.liquidacion y entrada en AppShell. Más una vista de historial con
  detalle (`/ventas/liquidaciones`).
- Pantalla en dos pasos: (1) Unidades: tabla de presentaciones (SKU · medida · sabor) con cargado
  (precargado), vendido, devuelto, merma, agotado; totales en vivo; semáforo de cuadre por fila.
  (2) Dinero: venta total calculada, efectivo, transferencia, crédito, cobro de saldos, gastos,
  efectivo entregado; efectivo esperado y diferencia en vivo (verde/ámbar/rojo según umbral).
- Acciones: Guardar borrador, Cerrar liquidación (confirmación que explica que alimenta el modelo),
  Corregir y Anular (con motivo). Si ya existe liquidación para fecha+ruta+vendedor, precargarla y
  mostrar «Corrección». Validación en cliente (>= 0, numérico, cuadres).
- Hooks TanStack Query (useLiquidacion, useGuardarLiquidacion, useCerrarLiquidacion...), que invalidan
  plan de carga, monitoreo, alertas y reportes. Textos en español; reutilizar Card, Campo, Button,
  AlertBanner. Panel administrativo mínimo para el parámetro de cierre de arranque del ETL.

PRUEBAS (matriz QA sección 5; cada caso antes de pasar al siguiente módulo; casos TC-LIQ-xx)
- tests/unit: DTO y servicio (negativos, fecha futura, producto duplicado, lista vacía, unidades que
  no cuadran, montos que no cuadran), cálculo de efectivo esperado y diferencia, checksum determinista,
  selección de fuente en training_service según `ml.fuente_reentrenamiento`; test_app_and_openapi al día.
- tests/integration (PostgreSQL migrado): borrador sin efecto en ventas_historicas; cierre escribe
  ventas_historicas con origen 'liquidacion'; re-envío idempotente / corrección con auditoría y nueva
  versión; anulación; llenado de demanda_real; encolado de evaluate_production; alerta de diferencia de
  caja; RBAC 401/403 por permiso; 409 EXCEL_DESHABILITADO; entrenamiento inicial con Excel intacto;
  reentrenamiento que incluye liquidaciones; comisiones/reportes siguen leyendo ventas correctas.
- frontend (vitest): render, cuadres en vivo, validación, envío, error de API, ocultamiento por permiso.
- E2E: Excel inicial → entrenamiento inicial → liquidación del día → demanda_real llena →
  evaluate_production → MAPE en Monitoreo → degradación → reentrenamiento con liquidaciones.

CIERRE
Ejecuta make lint, make test, make frontend-test y make frontend-build (equivalentes Windows en
CLAUDE.md). Resume qué cambió, decisiones de la ADR y desviaciones. No hagas commit salvo que se pida.
```

## Criterios de aceptación

- El admin liquida un día (unidades y dinero) en pocos minutos desde `/ventas/liquidacion`.
- Al cerrar, `ventas_historicas` contiene las filas con `origen='liquidacion'` y `demanda_real` queda llena.
- Se ve el cuadre de unidades y de caja; una diferencia sobre el umbral genera alerta.
- Corregir no duplica datos y deja auditoría y versión; anular revierte el efecto en el histórico.
- El entrenamiento inicial sigue saliendo de los Excel; los reentrenamientos usan base + liquidaciones.
- Con el arranque cerrado, `POST /etl/upload-excel` responde `EXCEL_DESHABILITADO`.
- `openapi.yaml` sincronizado, sin drift de Alembic y toda la suite en verde.
