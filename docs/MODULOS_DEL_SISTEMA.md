# Módulos del Sistema de Análisis Predictivo (ML)

**Cliente:** Desarrollos Comerciales del Sur, S.A. · **Tipo:** prototipo académico (tesis)
**Fuente técnica de verdad:** `docs/architecture/00-especificacion.md`

Este documento describe, módulo por módulo, qué hace el software, cómo lo hace, qué reglas de negocio aplica y quién puede usarlo. Se elaboró a partir del código (`backend/app`, `frontend/src`) y de `CLAUDE.md`.

---

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura en capas](#2-arquitectura-en-capas)
3. [Seguridad: autenticación, RBAC y usuarios](#3-seguridad-autenticación-rbac-y-usuarios)
4. [Catálogo y productos](#4-catálogo-y-productos)
5. [ETL: ingesta de ventas históricas](#5-etl-ingesta-de-ventas-históricas)
6. [Pipeline de Machine Learning](#6-pipeline-de-machine-learning)
7. [Predicción de demanda](#7-predicción-de-demanda)
8. [Monitoreo y gobernanza del modelo](#8-monitoreo-y-gobernanza-del-modelo)
9. [Worker predictivo](#9-worker-predictivo)
10. [Inventario y kardex](#10-inventario-y-kardex)
11. [Planificación de cargas de ruta](#11-planificación-de-cargas-de-ruta)
12. [Compras y pedidos a proveedor](#12-compras-y-pedidos-a-proveedor)
13. [Liquidación diaria de ventas](#13-liquidación-diaria-de-ventas)
14. [Alertas](#14-alertas)
15. [Reportes gerenciales](#15-reportes-gerenciales)
16. [Bitácora de auditoría](#16-bitácora-de-auditoría)
17. [Parámetros del sistema](#17-parámetros-del-sistema)
18. [Frontend (SPA)](#18-frontend-spa)
19. [Infraestructura y despliegue](#19-infraestructura-y-despliegue)
20. [Flujo de punta a punta](#20-flujo-de-punta-a-punta)

---

## 1. Visión general

El sistema ayuda a una distribuidora con **vendedores en ruta** a decidir **cuánto producto cargar a cada ruta cada día** y **cuánto comprar a proveedores**, apoyándose en un modelo de predicción de demanda. Además:

- Registra el cierre diario de ventas, unidades y dinero de cada ruta (liquidación).
- Usa esas liquidaciones como nueva fuente de datos para evaluar y reentrenar el modelo.
- Vigila que el modelo no se degrade y lo reentrena cuando hace falta.
- Mantiene inventario con trazabilidad completa (kardex), alertas, reportes y auditoría.

**Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · pandas · scikit-learn · XGBoost (LSTM opcional) · React 19 + Vite + Tailwind + TanStack Query.

**Procesos en ejecución:** API (`ds-backend`), Worker (`ds-worker`), base de datos (`ds-postgres`) y frontend (`ds-frontend`).

---

## 2. Arquitectura en capas

```
api  →  services  →  repositories  →  domain
```

| Capa | Ruta | Responsabilidad |
|---|---|---|
| **api** | `backend/app/api/v1/` | Routers HTTP, validación de DTOs, guardas RBAC. Sin reglas de negocio ni SQL. |
| **schemas** | `backend/app/schemas/` | DTOs Pydantic de entrada y salida. |
| **services** | `backend/app/services/` | Casos de uso y reglas de negocio. Llama a `ml/` solo vía `ml/contracts.py`. |
| **repositories** | `backend/app/repositories/` | Único lugar con consultas SQLAlchemy (uno por agregado). |
| **domain** | `backend/app/domain/` | Modelos ORM y enumeraciones (`enums.py`). |
| **ml** | `backend/app/ml/` | Preparación de datos, modelado, evaluación, inferencia y registro de artefactos. No importa `api/` ni `services/`. |
| **workers** | `backend/app/workers/` | Proceso en segundo plano; invoca `services/`, nunca repositorios. |
| **core** | `backend/app/core/` | Configuración, base de datos, seguridad, RBAC, errores, parámetros y contexto de petición. |

**Reglas transversales**

- Toda función pública de `services/` que reciba sesión lleva el decorador `@auditar` (ver [Bitácora](#16-bitácora-de-auditoría)).
- Los errores de negocio se lanzan como `AppError` con un código en español (por ejemplo `STOCK_INSUFICIENTE`, `CANTIDAD_EXCEDE_STOCK`, `PRODUCTO_EN_USO`).
- Estados y tipos se guardan como `varchar` + `CHECK` (no ENUM nativo de PostgreSQL), construidos desde `domain/enums.py`.
- El contrato OpenAPI (`docs/architecture/openapi.yaml`) se **genera** desde FastAPI con `make openapi` y se versiona.

---

## 3. Seguridad: autenticación, RBAC y usuarios

**Archivos:** `api/v1/auth.py`, `api/v1/users.py`, `services/auth_service.py`, `services/user_service.py`, `core/security.py`, `core/rbac.py`, `db/seeds/seed_rbac.py`.

### 3.1 Autenticación
- `POST /auth/login` valida credenciales y estado del usuario y emite un **JWT**.
- Respuestas: **401** si no está autenticado, **403** si está autenticado pero no tiene el permiso.

### 3.2 Control de acceso por permisos (RBAC)
Los permisos tienen el formato `recurso:accion`. Cada rol agrupa un conjunto de permisos.

| Rol | Permisos principales |
|---|---|
| **Administrador** | Todos los permisos. |
| **EncargadoInventario** | `etl:cargar`, `prediccion:consultar`, `inventario:leer`, `inventario:ajustar`, `productos:crear/editar/eliminar`, `alertas:leer`. |
| **EncargadoVentas** | `etl:cargar`, `prediccion:consultar`, `carga_ruta:generar`, `carga_ruta:aprobar`, `inventario:leer`, `alertas:leer`. |
| **EncargadoBodega** | `carga_ruta:despachar`, `inventario:leer`, `inventario:ajustar`, `alertas:leer`. |
| **EncargadoCompras** | `prediccion:consultar`, `inventario:leer`, `pedido_proveedor:gestionar`, `alertas:leer`. |
| **Gerente** | `reportes:leer`, `prediccion:consultar`, `carga_ruta:aprobar`, `inventario:leer`, `ml:metricas:leer`, `ml:reentrenar`, `alertas:leer`, `liquidaciones:leer`. |
| **Proveedor** | `pedido_proveedor:confirmar` (solo sobre sus propios pedidos). |
| **Liquidador** | `liquidaciones:registrar`, `liquidaciones:cerrar`, `liquidaciones:leer`. Responsable de registrar y cerrar la liquidación diaria por ruta y vendedor; no tiene `liquidaciones:corregir` (solo Administrador). |
| *Worker* | Aparece en la matriz de la especificación, pero no es un rol de inicio de sesión. |

**Permisos fuera de la matriz 1.4 original:** `reportes:leer`, `liquidaciones:*`, `etl:configurar`, `bitacora:leer` (solo Administrador) y `productos:crear|editar|eliminar` (Administrador y EncargadoInventario). Al añadir un permiso hay que actualizar el seed, la matriz de la especificación y `frontend/src/app/rbac.ts`.

### 3.3 Administración de usuarios
- Lista roles asignables, lista usuarios, **crea** y **edita** usuarios (datos, roles y rutas asignadas) y **cambia su estado** (activo/inactivo).
- Pantalla: `AdminUsersView`.
- Administrador inicial de bootstrap local: `admin@ds.gt` (la contraseña inicial debe rotarse tras el primer acceso).

---

## 4. Catálogo y productos

**Archivos:** `api/v1/catalog.py`, `api/v1/products.py`, `services/catalog_service.py`, `services/product_service.py` · **ADR-16**.

### 4.1 Catálogo de apoyo (solo lectura)
Expone **rutas**, **categorías** y **proveedores** para alimentar los filtros y formularios del frontend.

### 4.2 CRUD de productos
| Operación | Comportamiento |
|---|---|
| **Listar / obtener** | Consulta del catálogo con filtros. |
| **Crear** | Crea el producto y, en la misma transacción, su fila de `inventario` con stock **0**. El SKU se normaliza a mayúsculas y debe ser único. |
| **Editar** | Edición parcial (precio, costo, stock mínimo, categoría…). **No** toca existencias (eso es un ajuste con kardex) ni el estado. |
| **Dar de baja** | **Baja lógica** (`activo=false`), nunca `DELETE` físico, porque el producto está referenciado por ventas, cargas, kardex, pedidos y pronósticos. Se bloquea con **409 `PRODUCTO_EN_USO`** si tiene stock reservado o está en una carga vigente. Es idempotente. |
| **Reactivar** | Vuelve a `activo=true`. |

Nota: en los datos reales no hay proveedor, por lo que `productos.proveedor_id` es nullable (desviación documentada del ER).

---

## 5. ETL: ingesta de ventas históricas

**Archivos:** `api/v1/etl.py`, `services/etl_service.py`, `services/etl_lectura.py`.

Carga el histórico de ventas desde Excel hacia `ventas_historicas`. Solo se usa para el **arranque** del sistema.

### 5.1 Lectura y normalización (`etl_lectura.py`, sin acceso a BD)
Soporta dos formatos y ambos producen filas `FilaVenta`:

- **Tabular** (plantilla del contrato): una fila por venta con `fecha, ruta, sku, cantidad, precio_unitario` y `vendedor` opcional.
- **Ancho** (Excel comercial real, `VENTAS DIARIAS`): una hoja por vendedor/ruta, con un bloque de columnas por día (`ventas NN`). El producto se identifica por **medida + sabor** (no trae SKU) y se genera una clave `<medida>-<SABOR>` normalizada. El período se deduce del nombre del archivo (`VENTAS DIARIAS MARZO 2025.xlsx` → `2025-03`).

Normaliza fechas, decimales (2 decimales) y cabeceras (minúsculas, sin acentos). Los números de fila reportados son los de Excel (la cabecera es la fila 1).

### 5.2 Flujo del caso de uso (`etl_service.py`)
1. Calcula el **checksum SHA-256** del archivo.
2. Si ya fue cargado → **400** (duplicado).
3. Lee el archivo y **valida contra el catálogo**.
4. Si hay errores → **422**: el lote queda `rechazado` y se genera una alerta `etl_error`.
5. Si todo es válido → **carga idempotente** en `ventas_historicas` y **cálculo de comisiones** (`monto = monto_total × porcentaje / 100`, por cada venta con vendedor).

Estados de lote: `recibido → validado → rechazado | cargado`.

### 5.3 Endpoints
| Endpoint | Función |
|---|---|
| `POST /etl/upload-excel` | Sube y procesa un Excel. |
| `GET /etl/batches` | Historial de lotes cargados o rechazados. |
| `GET /etl/config` · `PUT /etl/config` | Política de datos: cierra (o reabre) el arranque y fija la fuente de reentrenamiento (`etl:configurar`). |

### 5.4 Política de datos (ADR-14)
Con `etl.carga_excel_habilitada=false`, el ETL responde **409**. A partir de ese momento la **liquidación diaria** es la única entrada de ventas.

---

## 6. Pipeline de Machine Learning

**Archivos:** `backend/app/ml/` (`pipeline.py`, `contracts.py`, `data_preparation/`, `modeling/`, `evaluation/`, `inference/`, `registry/`).

Sigue la metodología **CRISP-DM** (preparación → modelado → evaluación).

### 6.1 Preparación de datos (`data_preparation/`)
- **`feature_engineering.py`**: construye las características de la demanda diaria por serie (producto, ruta).
  - *Calendario:* día de semana, quincena, mes y estacionalidad cíclica (semanal y anual).
  - *Rezagos:* `lag_1`, `lag_7`, `lag_14`.
  - *Medias móviles:* `media_7`, `media_14`, `media_28`.
  - **Sin fuga de datos:** toda característica de la fecha `t` usa solo información anterior a `t`.
  - Completa con 0 los días sin venta dentro de cada serie.
  - Con cobertura parcial (ADR-14: Excel + liquidaciones separados por un hueco), solo rellena dentro de los rangos efectivamente cubiertos y los rezagos no cruzan el hueco.
- **`preprocessor.py`**: preprocesador serializable que fija el orden de las características y el código numérico de cada serie, garantizando el mismo esquema en entrenamiento e inferencia.
- **`splitters.py`**: particiones temporales **Walk-Forward** de ventana expansiva (nunca entrena con fechas posteriores a las de prueba).

### 6.2 Modelado (`modeling/`)
- **`model_factory.py`**: interfaz común y fábrica por algoritmo (`sklearn`, `xgboost`, `lstm`).
- **`sklearn_models.py`**: línea base con `RandomForestRegressor`.
- **`xgboost_models.py`**: `XGBRegressor` con método `hist`, submuestreo de filas/columnas y regularización L2; las predicciones se acotan en 0.
- **LSTM/Keras:** opcional (extra `lstm`).

### 6.3 Entrenamiento y evaluación (`pipeline.py`)
1. Preparación del calendario, rezagos y medias móviles.
2. **Backtest Walk-Forward** de 1 paso (3 folds, 14 días de prueba, mínimo 60 días de entrenamiento): produce métricas `backtest` y los **residuos** que calibran el intervalo al 95 %.
3. **Holdout recursivo:** reserva los últimos 14 días, entrena con lo anterior y pronostica con el mismo predictor de producción; produce métricas `holdout` globales y por producto, y la cobertura empírica del intervalo.
4. **Modelo final:** se reentrena con todo el histórico.

Las observaciones **censuradas** (producto agotado: la venta es un piso de la demanda real) pesan 0,5 en el entrenamiento.

### 6.4 Métricas (`evaluation/metrics.py`)
Definición única de **MAE**, **RMSE** y **MAPE**. El MAPE ignora los puntos con demanda real = 0 y devuelve `None` si no queda ninguno; se satura a un máximo por el tipo `numeric(7,3)`.

### 6.5 Registro de artefactos (`registry/`)
- **`artifact_store.py`:** guarda en `ml_artifacts/models/<algoritmo>/<versión>/` los archivos `model.bin`, `preprocessor.bin`, `feature_schema.json` y `training_report.json`. Cada versión es **inmutable** y se verifica con **SHA-256 antes de deserializar** (joblib/pickle ejecuta código al cargar).
- **`model_registry.py`:** sincroniza disco con las tablas `modelos_ml` y `metricas_evaluacion` y aplica **ADR-03**: exactamente **un modelo `produccion` por familia**. Promover archiva el vigente y promueve el nuevo en la misma transacción.

### 6.6 Contrato (`contracts.py`)
Fachada que es la **única** vía por la que `services/` llama a `ml/` (con importaciones perezosas). Define los tipos de intercambio y las excepciones: `DatosInsuficientes`, `HistorialInsuficiente`, `ArtefactoNoEncontrado`, `ArtefactoCorrupto`.

### 6.7 Caso de uso de entrenamiento (`training_service.py`)
Entrena, evalúa y registra un modelo con motivo `manual` o `programado`. Queda como **candidato**; solo pasa a producción con `promover=True`.

- **Entrenamiento inicial:** usa solo los Excel históricos.
- **Reentrenamientos:** usan la fuente indicada por `ml.fuente_reentrenamiento` (`excel_historico`, `excel_mas_liquidacion` o `liquidacion`).

---

## 7. Predicción de demanda

**Archivos:** `api/v1/predictions.py`, `services/prediction_service.py`, `ml/inference/predictor.py`, `ml/inference/cache.py`.

- `POST /predictions/demand` entrega el pronóstico de uno o varios productos para una ruta, con `fecha_base` y `horizonte_dias`.
- Usa el modelo en **producción**. Se mantiene en una **caché en memoria** cuya clave incluye el hash del modelo: si se promueve otra versión, se recarga validando el SHA-256 del disco.
- **Pronóstico recursivo multi-paso:** el modelo es de 1 paso; para el día `t+h` se usan el historial real y las predicciones ya emitidas de `t+1…t+h-1`.
- **Intervalo al 95 %:** cuantiles empíricos (2,5 % y 97,5 %) de los residuos walk-forward, ensanchados con el factor `f(h) = √(1 + 0,15·(h−1))` para reflejar el error acumulado.
- **Agregación por producto:** la demanda agregada es la suma de las rutas y su intervalo combina las semi-amplitudes por raíz de la suma de cuadrados (rutas independientes).
- Con `persistir=true` guarda los pronósticos en `pronosticos_demanda`, lo que alimenta el monitoreo de degradación.

---

## 8. Monitoreo y gobernanza del modelo

**Archivos:** `api/v1/ml.py`, `services/monitoring_service.py`, `services/retraining_service.py`, `services/job_service.py` · **ADR-03, ADR-04, ADR-08, ADR-12**.

### 8.1 Evaluación en producción (`monitoring_service`)
`evaluar_produccion` cruza `pronosticos_demanda` con las ventas reales por **periodos consecutivos y sin traslape**, guarda MAE/RMSE/MAPE en `metricas_evaluacion` (tipo `produccion`) y detecta degradación:

> Si el **MAPE supera el umbral** (`ml.mape_umbral`) durante **N periodos consecutivos** (`ml.periodos_consecutivos`), se crea la alerta **crítica** `mape_umbral` y se **encola un reentrenamiento** con motivo `degradacion`.

### 8.2 Reentrenamiento asíncrono (`retraining_service`)
- `solicitar` solo **encola** un job en `jobs_ml` (la API responde de inmediato).
- `ejecutar` (en el Worker) entrena un candidato por algoritmo, elige el de **menor MAPE** y lo **promueve solo si mejora estrictamente** al modelo productivo.
  - MAPE de referencia del productivo: el observado en producción (último periodo evaluado); si aún no hay, su MAPE de holdout.
  - MAPE del candidato: el de su holdout global.

### 8.3 Endpoints
| Endpoint | Función |
|---|---|
| `GET /ml/metrics` | Métricas y estado de degradación. |
| `POST /ml/models/retrain` | Solicita un reentrenamiento (`ml:reentrenar`). |
| `GET /ml/models` | Historial de la familia de modelos con su MAPE de holdout. |
| `GET /ml/jobs/{job_id}` | Estado de un job. |
| `GET /ml/config` · `PUT /ml/config` | Umbral MAPE y periodos consecutivos. |

Pantalla: `ModelMonitoringView` (`/monitoreo`).

---

## 9. Worker predictivo

**Archivos:** `workers/main.py`, `workers/scheduler.py`, `workers/jobs/evaluate_production.py`, `workers/jobs/retrain_model.py` · **ADR-04, ADR-12**.

Proceso independiente de la API: `python -m app.workers.main`.

- **`Planificador`** (`scheduler.py`): sondea la cola cada `WORKER_POLL_SEGUNDOS`; en cada ciclo atiende las evaluaciones y los reentrenamientos en cola y, si toca, evalúa producción cada `WORKER_EVALUACION_INTERVALO_SEGUNDOS`.
- **Job `evaluate_production`:** corre periódicamente y también como job `evaluacion_produccion` en cola (por ejemplo, encolado al cerrar una liquidación). Calcula el MAPE real vs. predicho y detecta degradación.
- **Job `retrain_model`:** consume la cola de reentrenamientos en `jobs_ml`, entrena en segundo plano y promueve solo si mejora.
- **Resiliencia:** un fallo en un job se registra y **no detiene** al Worker.
- Los jobs también están auditados con `@auditar` (origen `worker`).

Ciclo de vida de un job: `en_cola → en_ejecucion → completado | fallido`. Tipos: `reentrenamiento`, `evaluacion_produccion`, `pronostico_nocturno`.

---

## 10. Inventario y kardex

**Archivos:** `api/v1/inventory.py`, `services/inventory_service.py` · **ADR-16**.

### 10.1 Conceptos
- `stock_disponible = stock_actual − stock_reservado`.
- `kardex.saldo_resultante` es el `stock_actual` **físico** tras el movimiento (las reservas y liberaciones no lo alteran).
- Tipos de movimiento: `entrada`, `salida`, `ajuste`, `reserva`, `liberacion`.

### 10.2 Operaciones
| Operación | Qué hace |
|---|---|
| **Listar existencias** | Stock por producto; un producto sin fila de inventario cuenta como 0. |
| **Listar kardex** | Historial de movimientos con filtros. |
| `reservar` | Reserva stock bloqueando las filas; responde `CANTIDAD_EXCEDE_STOCK` si no alcanza. |
| `liberar` | Libera reservas (nunca por debajo de 0). |
| `confirmar_salida` | Salida física (despacho): consume la reserva y descuenta `stock_actual`. |
| `registrar_entrada` | Ingreso físico (recepción de pedido): incrementa `stock_actual` y registra la entrada. |
| `ajustar_existencias` | Ajuste manual (`POST /inventory/adjustments`): `incremento`, `decremento` o `fijar`, con **motivo obligatorio de 5 a 300 caracteres**. Bloquea con `FOR UPDATE`, no baja `stock_reservado` y guarda en kardex la `cantidad` **con signo** y el `motivo`. |
| `evaluar_cobertura` | Genera alertas cuando el stock disponible no cubre la demanda predicha. |

Las operaciones que mutan (`reservar`, `liberar`, `confirmar_salida`, `registrar_entrada`) solo hacen `flush`: el `commit` lo decide el caso de uso que las orquesta, para que el movimiento y el cambio de estado sean **atómicos**.

Pantalla: `InventoryView` (`/inventario`). Productos: `ProductsView` (`/productos`).

---

## 11. Planificación de cargas de ruta

**Archivos:** `api/v1/routes.py`, `services/load_plan_service.py` · **ADR-06, ADR-07**.

Genera el plan de **cuánto cargar a cada ruta para un día**, apoyado en la predicción.

### 11.1 Generar (`generar`)
1. Valida que la ruta exista y que **no haya otra carga vigente** para esa ruta y día (índice único parcial; `RUTA_NO_ENCONTRADA`, `RUTA_SIN_PRODUCTOS`).
2. Obtiene los productos con historial de ventas en la ruta.
3. Predice la demanda del día (horizonte 1 desde el día anterior, `persistir=true`).
4. Obtiene el stock disponible.
5. Calcula por producto:
   - `cantidad_sugerida = min(demanda_predicha, stock_disponible)` (**ADR-07**: el stock prevalece sobre la demanda).
   - `ajustado_por_stock = true` si `sugerida < demanda`.
6. Guarda la carga en estado `borrador` con su detalle y evalúa cobertura (puede crear alertas).

### 11.2 Estados
```
borrador → pendiente_aprobacion → aprobada | rechazada → despachada
```
- Estados **vigentes** (ocupan el cupo ruta/día): `borrador`, `pendiente_aprobacion`, `aprobada`.
- Aprobar y rechazar se aceptan desde `borrador` y `pendiente_aprobacion`. Rechazar también sobre una carga `aprobada` aún no despachada: **libera sus reservas**.
- **Nunca se despacha automáticamente** (ADR-06): el despacho es una acción explícita del EncargadoBodega (`carga_ruta:despachar`) que genera el kardex de salida.

### 11.3 Reglas de integridad
- `cantidad_aprobada <= stock_disponible_al_generar`.
- Ambas reglas están blindadas con `CHECK` en `detalle_cargas`; el servicio las valida antes y responde `400 CANTIDAD_EXCEDE_STOCK`.

### 11.4 Endpoints
`POST /routes/load-plans` (generar, enviar, aprobar o rechazar según `accion`), `GET /routes/load-plans`, `POST /routes/load-plans/{id}/dispatch`.

Pantalla: dashboard `SalesDashboardView` (`/`).

---

## 12. Compras y pedidos a proveedor

**Archivos:** `api/v1/purchasing.py`, `services/purchasing_service.py`.

### 12.1 Sugerencia de compra
```
cantidad_a_pedir = max(0, (demanda_proyectada + stock_minimo) − stock_actual)
```
La demanda proyectada es la **agregada de todas las rutas** para los próximos N días del modelo en producción. Si un producto no tiene pronóstico, se informa en `advertencias` y `pronostico_disponible=false`. Cada sugerencia incluye proveedor, `lead_time_dias` y costo unitario.

### 12.2 Ciclo de vida del pedido
```
borrador → enviado → confirmado → recibido      (+ cancelado desde borrador/enviado)
```
| Acción | Quién | Permiso |
|---|---|---|
| Crear y enviar | EncargadoCompras | `pedido_proveedor:gestionar` |
| Cancelar | EncargadoCompras | `pedido_proveedor:gestionar` |
| Confirmar | **Proveedor**, solo sobre sus propios pedidos | `pedido_proveedor:confirmar` |
| Recibir | EncargadoBodega / EncargadoInventario | `inventario:ajustar` (genera entrada en kardex e incrementa `stock_actual`) |

### 12.3 Endpoints
`GET /purchasing/suggestions`, `POST/GET /purchasing/orders`, `GET /purchasing/orders/{id}`, `POST …/send`, `POST …/cancel`, `PATCH …/confirm`, `POST …/receive`.

Pantalla: `PurchasingView` (`/compras`).

---

## 13. Liquidación diaria de ventas

**Archivos:** `api/v1/liquidaciones.py`, `services/liquidacion_service.py` · **ADR-14**.

Es **la única entrada de ventas tras el arranque**. El administrador o liquidador liquida cada día por **ruta y vendedor**, tanto en **unidades** como en **dinero**.

### 13.1 Estados
`borrador → cerrada | anulada`

- **Borrador:** puede guardarse **incompleto** y no afecta al modelo ni a `ventas_historicas`.
- **Cerrar:** acción explícita que valida los cuadres.

### 13.2 Cuadre de unidades
- `vendida + devuelta + merma` nunca puede superar lo cargado (también lo blinda un `CHECK`).
- **Para cerrar**: `cargada = vendida + devuelta + merma` en cada presentación.
- Si hay una carga despachada ese día, la precarga trae lo despachado; **editar `cantidad_cargada` exige justificación**. Sin carga, solo se avisa.
- No puede haber productos repetidos ni liquidaciones sin movimiento.

### 13.3 Cuadre de dinero
- `monto = cantidad vendida × precio` (a centavos).
- **Para cerrar**: `venta total = efectivo + transferencia + crédito`.
- **Caja:** `efectivo_esperado = efectivo + cobro de saldos − gastos`; `diferencia_caja = efectivo_entregado − esperado`.
- La diferencia **no bloquea el cierre**; si `|diferencia| > liquidacion.umbral_diferencia_caja`, se genera una alerta `diferencia_caja` indicando faltante o sobrante.

### 13.4 Efectos del cierre (en una sola transacción)
1. Crea un lote con `origen='liquidacion'`.
2. Escribe `ventas_historicas` (UPSERT por la restricción única) y sus **comisiones**.
3. **Rellena `demanda_real`** de los pronósticos de esa fecha/ruta/producto.
4. Calcula el cuadre de caja y, si corresponde, crea la alerta.
5. **Encola `evaluate_production`** (varias liquidaciones seguidas se coalescen en un solo job).
6. Audita el evento.

**No despacha ni toca el stock** (ADR-06): las devoluciones se muestran como «devolución esperada» para el flujo de inventario.

### 13.5 Corrección y anulación
- **Corregir** una liquidación cerrada: crea una nueva versión, hace UPSERT de ventas y recalcula `demanda_real`.
- **Anular:** si estaba cerrada, revierte su efecto en `ventas_historicas`. Libera el checksum original re-sellándolo.
- Cada liquidación tiene un **checksum SHA-256** determinista de `(fecha, ruta, vendedor, líneas)` para evitar duplicados.

### 13.6 Endpoints
| Endpoint | Función |
|---|---|
| `POST /liquidaciones` | Guardar borrador. |
| `GET /liquidaciones/precarga` | Datos para abrir la pantalla (lo despachado y la liquidación vigente). |
| `GET /liquidaciones` · `GET /liquidaciones/{id}` | Historial y detalle con cuadres calculados. |
| `POST …/{id}/cerrar` | Cerrar (`liquidaciones:cerrar`). |
| `POST …/{id}/corregir` · `POST …/{id}/anular` | Corrección y anulación (`liquidaciones:corregir`). |
| `GET /liquidaciones/config` · `PUT …/config` | Umbral de diferencia de caja. |

Pantallas: `LiquidacionDiariaView` (`/ventas/liquidacion`) y `LiquidacionesHistorialView` (`/ventas/liquidaciones`).

---

## 14. Alertas

**Archivos:** `api/v1/alerts.py`, `services/alert_service.py`.

Bandeja de alertas con visibilidad según los permisos del usuario. Permite **listar** y **reconocer** (`PATCH /alerts/{id}/acknowledge`).

| Tipo | Origen |
|---|---|
| `stock_bajo` | Stock disponible bajo el mínimo. |
| `quiebre_proyectado` | El stock no cubre la demanda predicha (al generar cargas o evaluar cobertura). |
| `mape_umbral` | Degradación del modelo (severidad **crítica**). |
| `etl_error` | Lote de Excel rechazado. |
| `diferencia_caja` | Diferencia de caja sobre el umbral en una liquidación. |

Severidades: `info`, `advertencia`, `critica`. Estados: `abierta → reconocida → resuelta`.

---

## 15. Reportes gerenciales

**Archivos:** `api/v1/reports.py`, `services/report_service.py`, `services/report_export.py` · permiso `reportes:leer`.

| Reporte | Contenido |
|---|---|
| `GET /reports/inventory-turnover` | **Rotación de inventario** e **índice de quiebres**. |
| `GET /reports/commissions` | **Liquidación de comisiones** por vendedor. |
| `GET /reports/sales-vs-forecast` | **Venta real vs. proyectada**. |
| `GET /reports/export` | Exportación del reporte pedido a **CSV** (UTF-8 con BOM para que Excel respete las tildes) o **Excel (.xlsx)**. |

Pantalla: `ReportsView` (`/reportes`).

---

## 16. Bitácora de auditoría

**Archivos:** `api/v1/bitacora.py`, `services/bitacora_service.py`, `core/contexto.py`, `domain/models/bitacora.py` · **ADR-15**.

- **`@auditar`** envuelve cada caso de uso público de `services/` y cada job del Worker: registra **quién, qué, argumentos saneados (sin secretos, truncados), resultado y duración**, tanto en éxito como en error.
- Un **middleware HTTP** registra cada petición (incluidos 401/403, que no llegan a un servicio) y fija el contexto de la petición mediante la cabecera `X-Request-ID`.
- Origen del registro: `http`, `servicio` o `worker`. Nivel: `INFO`, `WARNING`, `ERROR`.
- **Append-only:** un trigger de PostgreSQL bloquea `UPDATE`, `DELETE` y `TRUNCATE`.
- Escribe en una **sesión independiente**: un `rollback` del caso de uso no borra su rastro, y un fallo al registrar nunca rompe la operación de negocio (se informa por el logger `app.bitacora`).
- Consulta: `GET /bitacora`, permiso `bitacora:leer` (solo Administrador).
- En tests se apaga (`bitacora_habilitada=False`); se activa con `@pytest.mark.bitacora`.

---

## 17. Parámetros del sistema

**Archivos:** `core/parametros.py`, `repositories/parametro_repo.py`, tabla `parametros_sistema`.

| Parámetro | Efecto |
|---|---|
| `ml.mape_umbral` | MAPE a partir del cual se considera degradado el modelo. |
| `ml.periodos_consecutivos` | Periodos consecutivos sobre el umbral para disparar el reentrenamiento. |
| `ml.fuente_reentrenamiento` | Datos de reentrenamiento: `excel_historico`, `excel_mas_liquidacion` o `liquidacion`. |
| `etl.carga_excel_habilitada` | Si es `false`, el ETL responde 409. |
| `liquidacion.umbral_diferencia_caja` | Monto sobre el cual una diferencia de caja genera alerta. |
| `comisiones.porcentaje` | Porcentaje usado para calcular comisiones. |

Los seeds son **idempotentes** (`make seed`) y nunca pisan un cambio hecho por el negocio.

---

## 18. Frontend (SPA)

**Ubicación:** `frontend/src/` · React 19 + Vite + Tailwind 3 + React Router + TanStack Query + Axios. Los tipos se generan desde `openapi.yaml` (`npm run gen:api`).

### 18.1 Organización
`app/` (providers, `routes.tsx`, `rbac.ts`) · `views/` (una por pantalla) · `components/` · `hooks/` (TanStack Query, uno por módulo) · `services/` (clientes Axios por recurso) · `types/openapi.d.ts` (generado) · `utils/`.

### 18.2 Pantallas
| Ruta | Vista | Permiso que la habilita |
|---|---|---|
| `/login` | `LoginView` | Pública. |
| `/` | `SalesDashboardView` (o `Inicio`) | `carga_ruta:generar` o `carga_ruta:aprobar`. |
| `/monitoreo` | `ModelMonitoringView` | `ml:metricas:leer`. |
| `/compras` | `PurchasingView` | `pedido_proveedor:gestionar`, `pedido_proveedor:confirmar` o `inventario:ajustar`. |
| `/inventario` | `InventoryView` | `inventario:leer`. |
| `/productos` | `ProductsView` | `inventario:leer` (acciones por `productos:*`). |
| `/ventas/liquidacion` | `LiquidacionDiariaView` | `liquidaciones:registrar`. |
| `/ventas/liquidaciones` | `LiquidacionesHistorialView` | `liquidaciones:leer`. |
| `/politica-datos` | `PoliticaDatosView` | `etl:configurar` (solo Administrador). |
| `/etl` | `EtlUploadView` | `etl:cargar`. |
| `/reportes` | `ReportsView` | `reportes:leer`. |
| `/usuarios` | `AdminUsersView` | `usuarios:gestionar`. |
| `/acceso-denegado` | `AccessDeniedView` | — |

Toda ruta va dentro de `PermissionGate`. El mapa `PERMISOS_VISTA` de `rbac.ts` es un espejo de la matriz del servidor solo para no mostrar lo que no se puede usar; **el servidor sigue siendo la autoridad** (403).

---

## 19. Infraestructura y despliegue

Orquestado con Docker Compose (`infra/docker-compose.yml`):

| Servicio | Descripción |
|---|---|
| `ds-postgres` | PostgreSQL 16 (`postgres:16-alpine`), volumen `ds_pgdata`. |
| `ds-backend` | API FastAPI en `:8000` (`/docs`, `/health`); corre migraciones y seeds al arrancar. |
| `ds-worker` | Worker predictivo; volumen `ds_ml_artifacts` para los modelos. |
| `ds-frontend` | nginx en `:5173` con proxy `/api`. |

**Base de datos:** migraciones Alembic en `backend/app/db/migrations/versions/` (nunca se modifica una migración ya aplicada). PK `uuid`, `timestamptz` UTC, montos `numeric(14,2)`, cantidades `numeric(12,2)`, errores `numeric(7,3)`.

**Tablas principales:** `usuarios`, `roles`, `permisos`, `roles_permisos`, `usuarios_roles`, `categorias`, `proveedores`, `productos`, `rutas`, `inventario`, `kardex`, `etl_lotes`, `ventas_historicas`, `comisiones`, `liquidaciones_diarias`, `liquidacion_detalles`, `cargas_ruta`, `detalle_cargas`, `pedidos_proveedor`, `detalle_pedidos`, `modelos_ml`, `metricas_evaluacion`, `pronosticos_demanda`, `alertas`, `parametros_sistema`, `jobs_ml`, `bitacora`.

**Comandos útiles:** `make up`, `make migrate`, `make seed`, `make openapi`, `make test`, `make lint`, `make frontend-build` (ver `make help`).

---

## 20. Flujo de punta a punta

```
   Excel históricos ──► ETL ──► ventas_historicas ──► Entrenamiento inicial
                                                              │
                                                              ▼
                                                  Modelo en PRODUCCIÓN (ADR-03)
                                                              │
                         ┌────────────────────────────────────┤
                         ▼                                    ▼
        Carga de ruta (min(demanda, stock))        Sugerencia de compra
                         │                                    │
          aprobar ──► despachar (*)              pedido ► enviado ► confirmado ► recibido
                         │                                    │
                         ▼                                    ▼
             Kardex / Inventario  ◄───────────────────────────┘
                         │
                         ▼
       Liquidación diaria (ruta + vendedor) ──► cerrar
                         │
          ┌──────────────┼───────────────────┐
          ▼              ▼                   ▼
   ventas_historicas  demanda_real     alerta de caja
   + comisiones           │
                          ▼
              Worker: evaluate_production (MAPE real vs. predicho)
                          │
            MAPE > umbral × N periodos
                          ▼
              Reentrenamiento (retrain_model)
                          │
         promueve el candidato SOLO si mejora al productivo
```

(*) El despacho lo ejecuta el rol `EncargadoBodega`.

1. Los Excel históricos se cargan con el ETL y entrenan el modelo inicial.
2. El modelo predice la demanda; se genera la carga de ruta limitada por el stock disponible.
3. Un humano aprueba la carga y el EncargadoBodega la despacha (nunca es automático).
4. Al cierre del día, la liquidación registra las ventas reales y el cuadre de caja.
5. El Worker compara lo predicho con lo real y, si el modelo se degrada, lo reentrena y promueve el nuevo solo si es mejor.
6. Todo queda trazado en la bitácora de auditoría.
