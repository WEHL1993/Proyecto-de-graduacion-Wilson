# Sistema de Análisis Predictivo (DS Predictive) — Guía detallada de funcionamiento

> Cliente: **Desarrollos Comerciales del Sur, S.A.** (distribución de bebidas por rutas de venta).
> Proyecto de graduación: predicción de demanda con Machine Learning para planificar la carga de los camiones, controlar inventario, abastecer a proveedores y liquidar las ventas diarias.

Este documento explica **qué hace el sistema, qué hace cada pantalla (vista), cómo está organizada la base de datos y por qué se usa Docker**. Está escrito a partir del código real del repositorio (backend, frontend, migraciones, `docker-compose.yml`).

---

## Índice

1. [Qué es el sistema y qué problema resuelve](#1-qué-es-el-sistema-y-qué-problema-resuelve)
2. [Arquitectura general](#2-arquitectura-general)
3. [Seguridad: usuarios, roles, permisos y pantallas (RBAC)](#3-seguridad-usuarios-roles-permisos-y-pantallas-rbac)
4. [El flujo de negocio completo (de punta a punta)](#4-el-flujo-de-negocio-completo-de-punta-a-punta)
5. [Las vistas (pantallas) una por una](#5-las-vistas-pantallas-una-por-una)
6. [Funcionalidad que no tiene pantalla propia](#6-funcionalidad-que-no-tiene-pantalla-propia)
7. [El motor de Machine Learning](#7-el-motor-de-machine-learning)
8. [El Worker (proceso en segundo plano)](#8-el-worker-proceso-en-segundo-plano)
9. [La base de datos, tabla por tabla](#9-la-base-de-datos-tabla-por-tabla)
10. [Por qué se usa Docker](#10-por-qué-se-usa-docker)
11. [Cómo levantar y operar el sistema](#11-cómo-levantar-y-operar-el-sistema)
12. [Mapa de la API](#12-mapa-de-la-api)
13. [Decisiones arquitectónicas (ADR)](#13-decisiones-arquitectónicas-adr)
14. [Estructura del repositorio](#14-estructura-del-repositorio)

---

## 1. Qué es el sistema y qué problema resuelve

La empresa vende bebidas a través de **rutas** (camiones con un vendedor, un chofer y auxiliares). Cada día alguien decide **cuánto producto cargar en cada camión**. Si se carga de menos, se pierden ventas (quiebre); si se carga de más, hay devoluciones y merma.

El sistema ataca ese problema con cuatro ideas:

1. **Aprender del histórico de ventas** (al inicio, de archivos Excel; después, de la liquidación diaria) y entrenar un modelo que **predice la demanda diaria** por producto y por ruta.
2. **Sugerir el plan de carga** de cada ruta para el día siguiente: `cantidad sugerida = mínimo(demanda predicha, stock disponible)`. El stock disponible siempre manda sobre la predicción (no se promete lo que no hay).
3. **Mantener al humano al mando**: el modelo solo sugiere; una persona envía, aprueba o rechaza el plan. Nada se despacha automáticamente.
4. **Cerrar el ciclo**: al final del día se registra la **liquidación diaria** (qué se cargó, vendió, devolvió y cuánto dinero entró). Esos datos reales alimentan de nuevo al modelo, se mide su error (MAPE) y, si se degrada, el sistema pide reentrenarlo.

Además cubre inventario con kardex, catálogo de productos, abastecimiento con proveedores, reportes gerenciales (rotación, quiebres, comisiones), auditoría completa y control de acceso por roles.

---

## 2. Arquitectura general

El sistema es un **monolito modular en capas** (no microservicios; decisión ADR-01 porque el proyecto lo desarrolla una persona) con un proceso **Worker** separado.

```
 Navegador
     │  http://localhost:5173
     ▼
┌─────────────────────┐   /api/*    ┌──────────────────────────┐
│ Frontend (nginx)    │────────────▶│ Backend FastAPI (:8000)  │
│ React 19 + Vite SPA │  proxy      │ API REST v1 + JWT + RBAC │
└─────────────────────┘             └───────────┬──────────────┘
                                                │ SQLAlchemy
                    ┌───────────────────────────┼─────────────────────┐
                    ▼                           ▼                     ▼
          ┌──────────────────┐        ┌──────────────────┐   ┌─────────────────┐
          │ PostgreSQL 16    │◀───────│ Worker Python    │   │ Volumen         │
          │ (única fuente de │        │ (jobs ML en 2º   │──▶│ ml_artifacts    │
          │  verdad)         │        │  plano)          │   │ (modelos .pkl)  │
          └──────────────────┘        └──────────────────┘   └─────────────────┘
```

### Tecnologías

| Capa | Tecnología | Para qué |
|------|-----------|----------|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, React Router 7, TanStack Query 5, Recharts, Vitest | Interfaz web SPA, gráficos, caché de datos del servidor, pruebas |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic | API REST, acceso a datos, migraciones, validación |
| ML | pandas, scikit-learn (RandomForest), XGBoost | Entrenar y predecir la demanda |
| Base de datos | PostgreSQL 16 | Todos los datos del negocio y los metadatos de los modelos |
| Infra | Docker, Docker Compose, nginx | Empaquetado y ejecución reproducible |

### Capas del backend (`backend/app/`)

| Carpeta | Responsabilidad |
|---------|-----------------|
| `api/v1/` | Endpoints HTTP (routers). Solo reciben, validan permisos y delegan. |
| `services/` | **Casos de uso / lógica de negocio** (liquidación, plan de carga, ETL, compras, alertas…). Cada función pública está decorada con `@auditar` para dejar rastro en la bitácora. |
| `repositories/` | Consultas SQL (acceso a datos). Los servicios no escriben SQL directamente. |
| `domain/models/` | Modelos ORM (las tablas) y `enums.py` (estados y tipos permitidos). |
| `schemas/` | Contratos de entrada/salida (Pydantic). |
| `ml/` | Preparación de datos, modelos, evaluación, registro de modelos e inferencia. |
| `workers/` | Proceso en segundo plano (reentrenar, evaluar producción). |
| `core/` | Configuración, seguridad (JWT, hash), errores, contexto de auditoría, parámetros. |
| `db/migrations/` | Migraciones Alembic (historial versionado del esquema). |
| `db/seeds/` | Datos iniciales (roles, permisos, pantallas, admin) e importador de catálogos. |

Cada petición pasa por un *middleware* que le asigna un `request_id`, identifica al usuario por su JWT y registra la petición en la bitácora.

---

## 3. Seguridad: usuarios, roles, permisos y pantallas (RBAC)

### 3.1 Autenticación

- Se inicia sesión con **correo + contraseña** (`POST /auth/login`). Las contraseñas se guardan con *hash*, nunca en texto plano.
- El servidor devuelve un **JWT** que contiene el usuario, sus roles, sus permisos y la expiración (60 min por defecto, `JWT_EXPIRE_MINUTES`). El frontend lo envía en cada petición, de modo que el backend verifica permisos **sin consultar la BD en cada request** (ADR-05).
- Si la sesión expira, el login muestra el aviso «Su sesión expiró. Inicie sesión de nuevo.»
- Usuario inicial sembrado: `admin@ds.gt` (contraseña inicial de bootstrap `CambiarAdmin123`, **debe rotarse** tras el primer ingreso).

### 3.2 Permisos granulares

Los permisos tienen formato `recurso:acción`. Los sembrados son:

| Módulo | Permisos |
|--------|----------|
| Usuarios / roles | `usuarios:gestionar`, `roles:gestionar` |
| ETL / datos | `etl:cargar`, `etl:configurar` |
| Predicción | `prediccion:consultar` |
| Carga de ruta | `carga_ruta:generar`, `carga_ruta:aprobar`, `carga_ruta:despachar` |
| Inventario | `inventario:leer`, `inventario:ajustar` |
| Productos | `productos:crear`, `productos:editar`, `productos:eliminar` |
| Proveedores | `pedido_proveedor:gestionar`, `pedido_proveedor:confirmar` |
| Machine Learning | `ml:metricas:leer`, `ml:reentrenar` |
| Alertas / reportes | `alertas:leer`, `reportes:leer` |
| Liquidaciones | `liquidaciones:registrar`, `liquidaciones:cerrar`, `liquidaciones:corregir`, `liquidaciones:leer` |
| Auditoría | `bitacora:leer` |
| Catálogos (M02) | `catalogos:leer`, `catalogos:gestionar` |

### 3.3 Roles

| Rol | Descripción | Activo de fábrica |
|-----|-------------|-------------------|
| **Administrador** | Acceso total. Es rol de sistema (protegido: no se edita ni se desactiva). | Sí |
| **Gerente** | Aprueba cargas, monitorea modelos, ve reportes, liquidaciones y catálogos. | Sí |
| **Liquidador** | Registra y cierra la liquidación diaria. | Sí |
| EncargadoVentas | Genera/aprueba cargas de ruta, carga ETL. | No (heredado, se reactiva desde la matriz) |
| EncargadoInventario | Existencias, productos, ETL. | No |
| EncargadoBodega | Despacha cargas, ajusta inventario. | No |
| EncargadoCompras | Pedidos a proveedores. | No |
| Proveedor | Solo confirma **sus propios** pedidos (aislamiento por fila vía `usuarios.proveedor_id`). | No |

### 3.4 RBAC dinámico (ADR-19)

La **base de datos es la fuente de verdad** de la matriz roles × permisos y de qué pantalla exige qué permiso. Eso significa que el Administrador puede, desde la pantalla *Usuarios y Roles*, crear roles, activarlos/desactivarlos, asignarles color y editar sus permisos **sin tocar código ni redesplegar**. El seed solo *crea lo que falta*; nunca revierte lo que el administrador editó.

Cada rol tiene además una **pantalla de inicio** configurable. Una pantalla del menú se muestra si el usuario tiene **alguno** de los permisos asociados a ella (tabla `pantallas_permisos`).

### 3.5 Control en dos niveles

- **Backend**: cada endpoint exige un permiso; si falta responde 403.
- **Frontend**: `PermissionGate` oculta botones/rutas sin permiso y `AccessDeniedView` aparece si se entra por URL a algo no autorizado.

---

## 4. El flujo de negocio completo (de punta a punta)

```
 1. Arranque          2. Entrenamiento      3. Operación diaria            4. Cierre del día
┌──────────────┐   ┌─────────────────┐   ┌──────────────────────┐   ┌────────────────────┐
│ Catálogos:   │   │ Modelo ML con   │   │ Dashboard: generar   │   │ Liquidación diaria │
│ productos,   │──▶│ el histórico    │──▶│ plan de carga →      │──▶│ (unidades + dinero)│
│ rutas, equipo│   │ Excel → modelo  │   │ enviar → aprobar →   │   │ → cerrar           │
│ + ETL Excel  │   │ en producción   │   │ despachar            │   └─────────┬──────────┘
└──────────────┘   └─────────────────┘   └──────────────────────┘             │
                            ▲                                                  │
                            │       5. Aprendizaje continuo                    │
                            └─── Worker mide MAPE ◀── ventas reales ◀──────────┘
                                 Si degrada → alerta + reentrena
```

1. **Arranque**: se cargan catálogos (productos, rutas, empleados, equipo de ruta) y el histórico de ventas desde Excel (ETL).
2. **Entrenamiento**: se entrena un modelo (RandomForest o XGBoost) y se promueve a **producción**.
3. **Operación**: cada día, el encargado genera el plan de carga de cada ruta; el modelo sugiere, un humano aprueba, bodega despacha (se descuenta inventario con movimiento de kardex).
4. **Cierre**: el liquidador registra lo realmente cargado/vendido/devuelto y el dinero. Al **cerrar** se escriben las ventas reales, se calcula el cuadre de caja y se rellena la `demanda_real` de los pronósticos.
5. **Aprendizaje continuo**: el Worker compara pronóstico vs. real por periodos de 7 días. Si el error (MAPE) supera el umbral durante N periodos seguidos, crea una **alerta crítica** y encola un **reentrenamiento**.

**Política de datos (ADR-14):** el Excel es solo la línea base inicial. Una vez que el administrador «cierra el arranque», las ventas nuevas entran **únicamente** por la liquidación diaria y el endpoint de carga Excel responde 409.

---

## 5. Las vistas (pantallas) una por una

Estructura común: una barra superior (**Navbar**) con la identidad del usuario, la campana de alertas y el cierre de sesión; un menú lateral (**Sidebar**) construido dinámicamente desde la BD (agrupado en *Ventas, Analítica, Inventario, Catálogos, Datos, Administración*); y el contenido de la vista. Las notificaciones aparecen como *toasts*. Todas las rutas (salvo `/login`) están protegidas.

Resumen de rutas:

| Pantalla | Ruta | Clave | Grupo | Permiso que la habilita (basta uno) |
|----------|------|-------|-------|-------------------------------------|
| Login | `/login` | — | — | Pública |
| Dashboard de Ventas | `/` | `dashboard` | Ventas | `carga_ruta:generar`, `carga_ruta:aprobar` |
| Monitoreo de Modelos | `/monitoreo` | `monitoreo` | Analítica | `ml:metricas:leer` |
| Abastecimiento | `/compras` | `compras` | Inventario | `pedido_proveedor:gestionar`, `pedido_proveedor:confirmar`, `inventario:ajustar` |
| Inventario y Kardex | `/inventario` | `inventario` | Inventario | `inventario:leer` |
| Productos | `/productos` | `productos` | Inventario | `inventario:leer` |
| Liquidación Diaria | `/ventas/liquidacion` | `liquidacion` | Ventas | `liquidaciones:registrar` |
| Historial de Liquidaciones | `/ventas/liquidaciones` | `liquidaciones` | Ventas | `liquidaciones:leer` |
| Rutas y equipos (+ Personal) | `/catalogos/rutas`, `/catalogos/empleados` | `catalogos` | Catálogos | `catalogos:leer` |
| Carga de Datos (ETL) | `/etl` | `etl` | Datos | `etl:cargar` |
| Política de Datos | `/politica-datos` | `politica_datos` | Datos | `etl:configurar` |
| Reportes | `/reportes` | `reportes` | Analítica | `reportes:leer` |
| Usuarios y Roles | `/usuarios` | `usuarios` | Administración | `usuarios:gestionar` |
| Acceso denegado | `/acceso-denegado` | — | — | Cualquiera autenticado |

---

### 5.1 Login (`LoginView`)

**Para qué sirve:** puerta de entrada.

- Pantalla dividida: panel de marca («DS Predictive — Sistema de Análisis Predictivo — Desarrollos Comerciales del Sur, S.A.») y formulario «Bienvenido».
- Campos: correo y contraseña (con botón para mostrar/ocultar).
- Si el usuario intentaba abrir una pantalla concreta antes de autenticarse, tras el login vuelve a ella; si no, va a la **pantalla de inicio configurada para su rol**.
- Muestra errores de credenciales y el aviso de sesión expirada.

### 5.2 Dashboard de Ventas (`SalesDashboardView`) — la pantalla central

**Para qué sirve:** planificar la carga de cada camión con ayuda del modelo y gestionar su aprobación (ADR-06 y ADR-07).

**Controles:** selector de **ruta**, **fecha de operación** (por defecto, mañana) y **horizonte** de pronóstico.

**Qué muestra:**
- **Plan de carga** de la ruta/fecha: por cada producto, la *demanda predicha*, el *stock disponible al generar*, la *cantidad sugerida* (= `min(demanda, stock)`), y una marca cuando el plan quedó **ajustado por falta de stock**.
- **KPIs** calculados del plan (totales y productos limitados por stock).
- **Gráfico de demanda** (`DemandChart`) de un producto elegido: serie pronosticada con intervalo de confianza al 95 %. Solo se consulta si el rol tiene `prediccion:consultar`; si no, se muestra «Su rol no tiene permiso para consultar pronósticos».
- **Estado del modelo** en producción (si el rol puede ver métricas).
- **Alertas** de cobertura (stock bajo / quiebre proyectado) generadas al crear el plan.

**Acciones (según permiso y estado):**

| Acción | Quién | Efecto |
|--------|-------|--------|
| **Generar plan** | `carga_ruta:generar` | Crea la carga en estado `borrador` con la predicción del modelo. Solo puede haber **una carga vigente por ruta y día**. |
| **Recalcular** | generar | Rehace el plan con el stock actual. |
| **Enviar a aprobación** | generar | `borrador → pendiente_aprobacion`. |
| **Aprobar** | `carga_ruta:aprobar` | El aprobador marca los productos que se cargan y ajusta cantidades (lo aprobado **no puede exceder** el stock disponible al generar); las filas sin marcar se aprueban en 0. Reserva stock. |
| **Rechazar** | aprobar | Pide un motivo y libera las reservas. También permitido sobre una carga aprobada que aún no se despachó. |

Estados de la carga: `borrador → pendiente_aprobacion → aprobada | rechazada → despachada`.

### 5.3 Monitoreo de Modelos (`ModelMonitoringView`)

**Para qué sirve:** vigilar la precisión del modelo en producción y gobernar su reentrenamiento (ADR-08, ADR-12).

**Qué muestra:**
- Selector de periodo (días hacia atrás).
- **Indicadores**: modelo vigente, **MAE, RMSE, MAPE** global, y un **semáforo de degradación** (si el MAPE supera el umbral durante N periodos consecutivos).
- **Gráfico de tendencia del MAPE** (`MapeTrendChart`) por periodo de 7 días frente al umbral.
- **Tabla de peores productos** (mayor error) con tendencia.
- **Listado de modelos** registrados (versión, algoritmo, estado: candidato / producción / archivado / descartado, ventana de entrenamiento, fuentes de datos).

**Acciones:**
- **Configuración**: editar el umbral de MAPE (`ml.mape_umbral`, por defecto 12 %) y los periodos consecutivos (`ml.periodos_consecutivos`, por defecto 3).
- **Reentrenar** (solo `ml:reentrenar`): elegir algoritmos candidatos (sklearn / XGBoost), ventana de fechas «desde–hasta» (valida que «desde» < «hasta») y confirmar. Se crea un **job** en cola que el Worker ejecuta; la pantalla sigue su avance (en cola → en ejecución → completado/fallido). Un usuario que solo puede ver métricas ve el aviso «puede consultar las métricas, pero no reentrenar».

### 5.4 Abastecimiento y Pedidos (`PurchasingView`)

**Para qué sirve:** convertir la demanda proyectada en pedidos a proveedores y darles seguimiento.

**Sección 1 — Sugerencias de reabastecimiento**
- Selector de horizonte (días).
- Fórmula: `cantidad a pedir = máx(0, (demanda proyectada + stock mínimo) − stock actual)`, con la demanda agregada de todas las rutas.
- Las sugerencias se **agrupan por proveedor** (cada orden es de un solo proveedor). Por producto: stock actual, mínimo, demanda proyectada, sugerida y una columna editable «A pedir» con casilla para incluirla. Si no hay pronóstico para el producto, se marca «Sin pronóstico: solo punto de reorden».
- Fecha esperada precargada con el *lead time* del proveedor.
- Botones para **guardar como borrador** o **generar y enviar**.

**Sección 2 — Seguimiento de órdenes**
- Filtro por estado y línea de tiempo visual `borrador → enviado → confirmado → recibido` (o `cancelado`).
- Detalle desplegable con productos, cantidad, costo y subtotal.
- Acciones por permiso: **Enviar** y **Cancelar** (`pedido_proveedor:gestionar`), **Confirmar** con fecha estimada de entrega (`pedido_proveedor:confirmar`, el proveedor solo ve y confirma **sus** pedidos), **Recibir** (`inventario:ajustar`) — al recibir se genera una **entrada en el kardex** y sube el stock.

### 5.5 Inventario y Kardex (`InventoryView`)

**Para qué sirve:** consulta de existencias y trazabilidad de movimientos (solo lectura).

- **Existencias**: stock actual, reservado, **disponible** (`actual − reservado`) y mínimo por producto.
- **Alertas de stock bajo**: lista de productos con disponible por debajo del mínimo, ordenados del más crítico (mayor déficit) al menos crítico; si no hay, indica que todos están sobre su mínimo.
- **Visor de kardex**: filtro por producto y rango de fechas (valida que «Desde» no sea posterior a «Hasta»), paginado. Cada movimiento muestra tipo (entrada, salida, ajuste, reserva, liberación), cantidad, saldo resultante, referencia (carga, pedido, ajuste, ETL) y el motivo si fue ajuste manual.

### 5.6 Productos (`ProductsView`)

**Para qué sirve:** catálogo maestro (ADR-16).

- Búsqueda por texto, filtro por categoría y por estado (activos / dados de baja), paginación.
- Tabla: producto (SKU y nombre), categoría, **presentación** legible (p. ej. «6 × 3030 ml · COLA»), precio, stock, disponible, mínimo.
- **Crear / editar** producto (modal): SKU, nombre, categoría, proveedor (opcional), precio de venta, costo, stock mínimo, unidades por paquete, medida en ml y sabor. Las validaciones del formulario reflejan las reglas del backend.
- **Ajuste manual de stock** (modal): tres modalidades — **incrementar**, **decrementar** o **fijar** — con **motivo obligatorio**. Muestra el stock que quedaría; no deja bajar el stock por debajo de lo reservado. Genera un movimiento de kardex.
- **Baja lógica / reactivación**: un producto no se borra; se da de baja (si está en uso, el servidor informa por qué: `PRODUCTO_EN_USO`, `STOCK_INSUFICIENTE`).
- Cada acción aparece solo con el permiso `productos:crear|editar|eliminar` / `inventario:ajustar`.

### 5.7 Liquidación Diaria (`LiquidacionDiariaView`)

**Para qué sirve:** registrar al cierre del día, por **ruta y vendedor**, lo que pasó con la mercancía y el dinero. Es la **fuente de datos del modelo** tras el arranque (ADR-14).

**Se trabaja en dos pasos:**

**Paso 1 — Unidades.** Tabla por presentación con: *Cargado, Vendido, Devuelto, Merma, Agotado, Cuadre* y justificación. Se precarga con lo **despachado a la ruta** ese día. Reglas:
- `vendido + devuelto + merma` nunca puede exceder lo cargado.
- Para **cerrar**, debe cuadrar exactamente: `cargado = vendido + devuelto + merma`.
- Si hay carga despachada y se edita lo cargado, se exige **justificación**.
- Marcar **Agotado** indica que el producto se acabó antes de terminar la ruta: esa venta es solo un *piso* de la demanda real (dato **censurado**) y el modelo la pondera menos al entrenar.

**Paso 2 — Dinero.** Venta total (calculada = Σ vendido × precio), desglose de pago **efectivo / transferencia / crédito**, cobro de saldos anteriores, gastos de ruta y efectivo entregado. El sistema calcula:
- `efectivo esperado = efectivo + cobro de saldos − gastos`
- `diferencia de caja = efectivo entregado − efectivo esperado`
- Control: `venta = efectivo + transferencia + crédito`.
- Se muestra la **devolución esperada** (informativa: la pantalla nunca toca el stock).

**Acciones:**
- **Guardar borrador** (`liquidaciones:registrar`): puede quedar incompleto y no afecta al modelo.
- **Cerrar** (`liquidaciones:cerrar`): valida los cuadres y, en **una sola transacción**: crea un lote `origen=liquidacion`, escribe `ventas_historicas` y comisiones, rellena la `demanda_real` de los pronósticos, calcula la caja (genera alerta `diferencia_caja` si supera el umbral), encola la evaluación del modelo y audita.
- **Corregir** (`liquidaciones:corregir`): sobre una liquidación cerrada crea una **nueva versión**, recalcula la demanda real y deja auditoría.
- **Anular** (`liquidaciones:corregir`): pide motivo; si estaba cerrada, revierte su efecto en el histórico.
- Solo existe **una liquidación vigente** por fecha + ruta + vendedor.

### 5.8 Historial de Liquidaciones (`LiquidacionesHistorialView`)

**Para qué sirve:** auditoría y consulta (típicamente Administrador y Gerente).

- Filtros: rango de fechas, ruta, estado (borrador / cerrada / anulada). Paginado.
- Tabla: fecha, ruta, vendedor, unidades, venta, **diferencia de caja**, estado.
- Botón de detalle (modal): líneas por SKU (cargado, vendido, devuelto, merma, monto), venta total, efectivo esperado/entregado, diferencia de caja y devolución esperada.

### 5.9 Rutas y equipos (`RoutesAdminView` + `RouteTeamView`) — M02

**Rutas** (`/catalogos/rutas`): alta, edición, activación/desactivación de rutas. El **código** de la ruta no cambia después de creado (el ETL identifica la ruta por él; se guarda en mayúsculas). La tabla muestra zona y **equipo vigente**. Dos paneles de calidad de datos:
- **Equipos incompletos**: rutas activas sin vendedor o cuyo reparto no suma 100 %.
- **Rutas desalineadas**: diferencias entre el vendedor de la ruta y el del equipo vigente.

**Equipo de la ruta** (`/catalogos/rutas/:rutaId/equipo`): editor de integrantes con **empleado, rol en la ruta (vendedor / chofer / auxiliar) y porcentaje de reparto**.
- Reglas: el reparto **debe sumar 100 %** (indicador verde al cuadrar, rojo con la diferencia); **un solo vendedor vigente** por ruta; sin empleados repetidos.
- Al guardar se indica la fecha «vigente desde». Los integrantes anteriores **no se borran**: se cierran con una fecha «vigente hasta» y quedan en el historial de la pantalla (tabla «Integrantes anteriores»).
- Este reparto es la base para repartir comisiones (M06).

### 5.10 Personal de ruta (`EmployeesView`) — M02

Catálogo de **empleados** (vendedores, choferes, auxiliares): búsqueda, filtro activos / dados de baja, alta, edición, baja lógica y reactivación. Un empleado **no es lo mismo que un usuario del sistema**: tiene un vínculo opcional a un usuario (un chofer no necesita cuenta de acceso). Si el empleado está en un equipo vigente, la baja se bloquea (`EMPLEADO_EN_USO`).

### 5.11 Carga de Datos / ETL (`EtlUploadView`)

**Para qué sirve:** cargar el histórico de ventas desde Excel (la línea base del modelo).

- **Zona de arrastrar y soltar** `.xlsx` (máx. 20 MB) o seleccionar archivo; barra de progreso.
- Opciones: **hoja** (para libros multihoja), **periodo** `YYYY-MM` y **modo de carga**: *Estricto* (rechaza el lote completo ante un error) o *Parcial* (carga las filas válidas).
- Admite dos formatos (ADR-09): **tabular** (`fecha, ruta, sku, cantidad, precio_unitario[, vendedor]`) y **ancho** (el Excel comercial real *VENTAS DIARIAS*: una hoja por vendedor/ruta y un bloque de columnas por día).
- Tras enviar: si hay errores muestra una tabla con **hoja, fila, columna, valor y detalle** del problema; si todo va bien, el resumen del lote (filas totales, válidas, rechazadas).
- **Detección de duplicados** por checksum SHA-256: un mismo archivo no puede cargarse dos veces («Lote duplicado»). Un lote rechazado sí se puede reenviar.
- **Historial de lotes**: fecha, archivo, usuario, filas válidas/rechazadas y estado (recibido, validado, rechazado, cargado).
- Si el arranque está cerrado (ver Política de Datos), la pantalla queda **deshabilitada** con un aviso: «Carga de Excel deshabilitada».
- Efectos: escribe `ventas_historicas` de forma idempotente (UPSERT), calcula **comisiones** (`monto × porcentaje`) y, si hay rechazo, crea una alerta `etl_error`.

### 5.12 Política de Datos (`PoliticaDatosView`)

**Para qué sirve:** panel mínimo del Administrador para gobernar de dónde aprende el modelo (ADR-14).

- **Cierre del arranque ETL** (acción destructiva con confirmación): con el arranque cerrado, `POST /etl/upload-excel` responde 409 y las ventas nuevas solo entran por liquidación. Los datos ya cargados no se tocan. Se puede reabrir.
- **Fuente de reentrenamiento**: `excel_historico`, `excel_mas_liquidacion` (por defecto) o `liquidacion`.
- **Umbral de diferencia de caja** (por defecto 10,00): a partir de él, la liquidación genera alerta.
- Todos los cambios quedan auditados.

### 5.13 Reportes gerenciales (`ReportsView`)

**Para qué sirve:** indicadores para la gerencia (ADR-13).

- Filtros: rango de fechas y ruta (sin fechas = últimos 30 días hasta el último dato; las comisiones se liquidan por mes).
- **Indicadores** (tarjetas) y tres gráficos: **barras de venta real vs. proyectada por ruta**, **líneas de venta diaria real vs. proyectada** y **barras de comisión por agente**.
- **Tabla de comisiones** por vendedor y periodo (vendido, comisión, %).
- **Tabla de rotación y quiebres por ruta**: unidades vendidas, costo de ventas, rotación, líneas ajustadas, **índice de quiebre** y unidades no cubiertas.
- **Exportación** a **Excel (.xlsx)** o **CSV**.

### 5.14 Usuarios y Roles (`AdminUsersView`)

**Para qué sirve:** administración de accesos. Tiene pestañas (según permisos):

1. **Usuarios**: búsqueda, filtro por rol y estado; alta/edición con nombre, correo, contraseña, **roles** y **rutas comerciales asignadas** (una ruta tiene un solo vendedor: asignarla aquí la quita de su titular). Activar/desactivar cuentas. Salvaguardas: no se puede desactivar al último administrador ni a uno mismo; el rol Proveedor exige asociar un proveedor; correo único.
2. **Matriz de permisos** (`roles:gestionar`): tabla permisos × roles editable desde la BD, alta de roles, activar/desactivar, color.
3. **Acceso a pantallas**: qué pantalla exige qué permiso y la pantalla de inicio de cada rol.

### 5.15 Acceso denegado (`AccessDeniedView`)

Mensaje «Su rol no tiene permiso para ver esta sección.» Aparece al entrar por URL a una pantalla no autorizada, o como destino del inicio cuando el rol no puede ver el dashboard ni tiene pantalla de inicio configurada.

### Componentes transversales del frontend

| Componente | Función |
|-----------|---------|
| `AppShell`, `Navbar`, `Sidebar` | Estructura de página y menú dinámico por permisos |
| `AlertBanner` | Banner de avisos/errores/alertas |
| `PermissionGate` | Muestra u oculta contenido según permisos / pantalla |
| `LoadPlanTable`, `DemandChart`, `MapeTrendChart` | Tabla del plan de carga y gráficos |
| `Modal`, `Button`, `Card`, `PasswordInput`, `PestanasRutas` | UI reutilizable |
| `toast`, `feedback` | Notificaciones |
| `AuthProvider` | Sesión, JWT y helpers `can()` / `puedeVer()` |
| `hooks/*` + `services/*` | Un hook (TanStack Query) y un cliente API por módulo |

---

## 6. Funcionalidad que no tiene pantalla propia

- **Bitácora de auditoría** (`GET /bitacora`, permiso `bitacora:leer`): existe la API y el registro completo (ADR-15), pero **no hay pantalla** en el menú actual.
- **Despacho de carga** (`carga_ruta:despachar`, EncargadoBodega): existe en el backend (`aprobada → despachada`, con salida de kardex); el menú actual no expone una vista dedicada para ello.
- **Alertas** (`GET /alerts`, `PATCH` para reconocer): se consumen desde el banner/navbar, no desde una pantalla propia. Cada tipo de alerta solo lo ven los roles con permisos de su dominio: `stock_bajo`, `quiebre_proyectado`, `mape_umbral`, `etl_error`, `diferencia_caja`.
- **Importador de catálogos** (`make seed-catalogos`): carga productos/alias desde los Excel de `data/raw`, con propuesta y empate de alias (nombre en el Excel ↔ producto). Por defecto corre en *dry-run*; para escribir se añade `ARGS=--aplicar`.

---

## 7. El motor de Machine Learning

### 7.1 Qué se predice

La **demanda diaria** (unidades) por **serie = (producto, ruta)**, y la agregada (todas las rutas) para compras. Se usa **un único modelo de 1 paso** y el pronóstico a varios días es **recursivo** (cada predicción alimenta los rezagos de la siguiente).

### 7.2 Características (features)

- **Rezagos**: ventas de hace 1, 7 y 14 días.
- **Medias móviles**: 7, 14 y 28 días.
- **Calendario**: día de la semana, día del mes, quincena, fin de quincena, mes y codificaciones cíclicas (seno/coseno) de semana y año.
- Ninguna característica usa información futura (no hay *data leakage*).
- Se necesita historia mínima por serie (28 días para predecir; ~60 para entrenar con el backtest por defecto).

### 7.3 Algoritmos

`sklearn` (RandomForest) y `xgboost`, a través de una fábrica común (`model_factory`). Existe el valor `lstm` en el enum como reserva, sin implementar.

### 7.4 Pipeline de entrenamiento (CRISP-DM)

1. **Preparación**: calendario completo por serie, rezagos, medias móviles.
2. **Backtest Walk-Forward** (ventana expansiva): produce métricas `backtest` y los residuos que calibran el intervalo.
3. **Holdout recursivo**: se reserva el último tramo (14 días), se entrena con lo anterior y se predice con el mismo predictor de producción → métricas `holdout` globales y por producto.
4. **Modelo final**: se reentrena con todo el histórico.

Intervalo de predicción al **95 %**: cuantiles de los residuos del backtest, ensanchados con el horizonte.

### 7.5 Datos censurados y cobertura (ADR-14)

- Cuando un producto se **agota**, la venta es un piso de la demanda: esa observación se marca *censurada* y pesa la mitad en el entrenamiento.
- Si hay un hueco temporal entre el Excel histórico y las liquidaciones, el calendario solo se completa dentro de los rangos con información y los rezagos no cruzan el hueco.

### 7.6 Registro y gobernanza de modelos

- Cada modelo entrenado se registra en `modelos_ml` con algoritmo, versión, hiperparámetros, esquema de features, ventana de datos, fuentes de datos y un **hash** del artefacto.
- El artefacto serializado se guarda en disco (volumen `ml_artifacts`), no en la BD (ADR-02).
- Estados: `candidato → produccion → archivado | descartado`. **Solo un modelo en producción por nombre** (índice único parcial; ADR-03) y promover otro archiva el anterior.
- Entrenar por línea de comandos: `python scripts/train_model.py --algoritmo xgboost --promover [--min-train-dias N]`.

### 7.7 Monitoreo (ADR-08 / ADR-12)

- **Periodo de evaluación** = 7 días consecutivos sin traslape.
- Para cada periodo se cruzan los `pronosticos_demanda` con las ventas reales y se guarda **MAE, RMSE y MAPE** (global y por producto) en `metricas_evaluacion`.
- **Degradación**: si el MAPE supera `ml.mape_umbral` durante `ml.periodos_consecutivos` periodos seguidos → alerta crítica `mape_umbral` + job de reentrenamiento con motivo `degradacion`.
- Los días de producto agotado (`demanda_censurada`) no se evalúan como error.

---

## 8. El Worker (proceso en segundo plano)

Proceso Python independiente (`python -m app.workers.main`), mismo código que el backend pero otro contenedor. **No usa broker** (Celery/Redis): usa la tabla `jobs_ml` como cola (ADR-04), lo que reduce infraestructura.

Cada ciclo (cada `WORKER_POLL_SEGUNDOS`, 15 s por defecto):
1. Si toca (cada `WORKER_EVALUACION_INTERVALO_SEGUNDOS`, 6 h por defecto) → **evaluar producción** (MAPE vs. umbral).
2. Atender evaluaciones encoladas (p. ej. tras cerrar una liquidación; varias seguidas se coalescen en un solo job).
3. Ejecutar **reentrenamientos** pendientes (`retrain_model`).

Un fallo en un job se registra en la bitácora y **no detiene** al Worker. Sus registros llevan origen `worker`.

---

## 9. La base de datos, tabla por tabla

### 9.1 Motor y convenciones

- **PostgreSQL 16**, base `ds_predictive`, usuario `ds_user`.
- **Zona horaria UTC** (se fija al crear la BD con `infra/postgres/init/01-database.sql`).
- **Migraciones con Alembic** (7 hasta ahora): `0001` esquema inicial → `0002` liquidación diaria → `0003` bitácora → `0004` motivo de ajuste en kardex → `0005` renombrar roles y liquidador → `0006` catálogos y equipos de ruta → `0007` RBAC por pantallas y roles activos.
- Llaves primarias `uuid` (`gen_random_uuid()`) para entidades de negocio y `bigint IDENTITY` para tablas de alto volumen (kardex, ventas, pronósticos, bitácora).
- Montos `numeric(14,2)`, cantidades `numeric(12,2)`, porcentajes de error `numeric(7,3)`.
- Los estados (enums) se guardan como `varchar` + `CHECK`, **no** como ENUM nativo, para facilitar las migraciones.
- La **integridad se refuerza en la BD**, no solo en el código: restricciones `CHECK` (p. ej. `cantidad_sugerida = LEAST(predicha, stock)`; `vendida + devuelta + merma ≤ cargada`; una liquidación cerrada cumple `venta = efectivo + transferencia + crédito`), índices únicos parciales y triggers.

### 9.2 Autenticación y RBAC

| Tabla | Contenido |
|-------|-----------|
| `usuarios` | Cuentas: email único, `password_hash`, nombre, `proveedor_id` (solo rol Proveedor), `activo`, `ultimo_login`. |
| `roles` | Roles con `activo`, `es_sistema`, `requiere_proveedor`, `color` y `pantalla_inicio_id`. |
| `permisos` | Códigos `recurso:acción`, descripción y `modulo`. |
| `usuarios_roles` | Usuario ↔ rol (N:M). |
| `roles_permisos` | Rol ↔ permiso (N:M): **la matriz editable**. |
| `pantallas` | Entradas del menú: clave, etiqueta, ruta, prefijo, grupo, orden. |
| `pantallas_permisos` | Qué permisos habilitan cada pantalla. |

### 9.3 Catálogos y existencias

| Tabla | Contenido |
|-------|-----------|
| `categorias` | Categorías (jerárquicas: `categoria_padre_id`). |
| `proveedores` | Nombre, NIT único, email, `lead_time_dias`, activo. |
| `productos` | SKU único, nombre, categoría, proveedor (nullable porque los Excel no lo traen), precio, costo, `stock_minimo`, `unidades_por_paquete`, `medida_ml`, `sabor`, activo. |
| `producto_alias_excel` | Nombre con que el producto aparece en el Excel comercial (`<medida>-<SABOR>`); permite al ETL emparejar sin depender del SKU. |
| `rutas` | Código único, nombre, zona, `vendedor_id`, activa. |
| `empleados` | Personal de ruta (vendedor, chofer, auxiliar) con `usuario_id` opcional y único. |
| `equipo_ruta` | Integrantes de una ruta: rol, `porcentaje_reparto` (0–100), `vigente_desde/hasta`. Índices únicos parciales: un solo vendedor vigente por ruta y un empleado una vez por ruta. |
| `inventario` | Una fila por producto: `stock_actual`, `stock_reservado` (checks: reservado ≤ actual, no negativos). |
| `kardex` | Libro de movimientos: tipo (entrada/salida/ajuste/reserva/liberación), cantidad, `saldo_resultante`, referencia, usuario, fecha y `motivo`. |

### 9.4 Operación comercial

| Tabla | Contenido |
|-------|-----------|
| `cargas_ruta` | Plan de carga: ruta, fecha, estado, modelo usado, quién generó/aprobó. Índice único parcial: **una carga vigente por ruta y día**. |
| `detalle_cargas` | Por producto: demanda predicha, stock al generar, cantidad sugerida, aprobada y bandera `ajustado_por_stock`. |
| `pedidos_proveedor` | Pedido a un proveedor: estado, fechas, total. |
| `detalle_pedidos` | Productos del pedido, cantidad, costo y la alerta que lo originó. |

### 9.5 Histórico de ventas y liquidación

| Tabla | Contenido |
|-------|-----------|
| `etl_lotes` | Cada carga de datos: archivo, **checksum SHA-256 único**, estado, conteos, errores (JSONB) y `origen` (`excel_historico` / `liquidacion`). |
| `ventas_historicas` | Ventas diarias por fecha + producto + ruta + vendedor (único, con `NULLS NOT DISTINCT` para que la recarga sea idempotente). **Es el dataset del modelo.** |
| `comisiones` | Comisión por venta y vendedor, con periodo `YYYY-MM`, porcentaje y monto. |
| `liquidaciones_diarias` | Cabecera de la liquidación: estado, versión, desglose de pago, efectivo esperado/entregado, diferencia de caja, historial JSONB. Una vigente por fecha/ruta/vendedor. |
| `liquidacion_detalles` | Líneas por presentación: cargado, vendido, devuelto, merma, precio, monto, `agotado`, justificación. |

### 9.6 Machine Learning y operación del sistema

| Tabla | Contenido |
|-------|-----------|
| `modelos_ml` | Registro de modelos: algoritmo, versión, estado, ruta y hash del artefacto, hiperparámetros, features, ventana, fuentes. |
| `metricas_evaluacion` | MAE, RMSE, MAPE por modelo/producto/periodo y tipo (holdout, backtest, producción). |
| `pronosticos_demanda` | Pronósticos persistidos, con intervalo, `demanda_real` (rellenada después) y `demanda_censurada`. |
| `alertas` | Alertas con tipo, severidad (info/advertencia/crítica) y estado (abierta/reconocida/resuelta). |
| `jobs_ml` | Cola del Worker: tipo, estado, parámetros, resultado y error. |
| `parametros_sistema` | Configuración en clave/valor JSONB: `ml.mape_umbral`, `ml.periodos_consecutivos`, `comisiones.porcentaje`, `etl.carga_excel_habilitada`, `ml.fuente_reentrenamiento`, `liquidacion.umbral_diferencia_caja`. |
| `bitacora` | Auditoría **append-only** (ver abajo). |

### 9.7 La bitácora (ADR-15)

Registro de **todo** lo que ejecuta el sistema: nivel, origen (`http`/`servicio`/`worker`), operación, acción, resultado, usuario, IP, `request_id` (une la petición con sus servicios), duración y parámetros **saneados** (se ocultan contraseñas, tokens, hashes). Propiedades clave:
- Un **trigger** bloquea `UPDATE`, `DELETE` y `TRUNCATE`: nadie puede alterar el rastro.
- **No tiene FK a usuarios**: el rastro sobrevive aunque se borre el usuario.
- Se escribe en una **sesión independiente**: aunque la operación de negocio haga *rollback*, el registro queda; y un fallo al registrar nunca rompe la operación.

### 9.8 Cómo se relacionan (resumen)

```
usuarios ─< usuarios_roles >─ roles ─< roles_permisos >─ permisos
                               roles ── pantalla_inicio ── pantallas ─< pantallas_permisos >─ permisos

categorias ─< productos >─ proveedores        productos ─< producto_alias_excel
productos ─1:1─ inventario     productos ─< kardex
rutas ─< equipo_ruta >─ empleados ─(opcional)─ usuarios

rutas ─< cargas_ruta ─< detalle_cargas >─ productos         cargas_ruta ─ modelos_ml
proveedores ─< pedidos_proveedor ─< detalle_pedidos >─ productos

etl_lotes ─< ventas_historicas >─ productos, rutas, usuarios(vendedor)
ventas_historicas ─< comisiones
rutas/usuarios ─< liquidaciones_diarias ─< liquidacion_detalles >─ productos
liquidaciones_diarias ─ etl_lotes (al cerrar)

modelos_ml ─< metricas_evaluacion       modelos_ml ─< pronosticos_demanda >─ productos, rutas
alertas ─ productos / modelos_ml        jobs_ml ─ modelos_ml
```

---

## 10. Por qué se usa Docker

### 10.1 La idea en una frase

**Docker empaqueta cada pieza del sistema (base de datos, API, worker, web) con todo lo que necesita para funcionar, de modo que se levanta igual en cualquier computadora con un solo comando.**

### 10.2 Qué problemas resuelve en este proyecto

| Problema sin Docker | Solución con Docker |
|--------------------|---------------------|
| Instalar a mano PostgreSQL 16, Python 3.12, Node 22, nginx y sus librerías en cada máquina (la tesis se defiende en otra PC, se prueba en otra, etc.). | `docker compose up` y listo. Versiones fijadas: `postgres:16-alpine`, `python:3.12-slim`, `node:22-alpine`, `nginx:1.27-alpine`. |
| "En mi máquina sí funciona": diferencias de SO (aquí se desarrolla en Windows), de versiones de librerías, de variables de entorno. | Todos ejecutan el mismo contenedor Linux. |
| XGBoost necesita la librería nativa `libgomp1` (OpenMP), difícil de instalar bien en cada SO. | Está instalada en la imagen del backend (`Dockerfile`). |
| Que el backend arranque **antes** de que la BD esté lista y falle. | `depends_on` con *healthcheck*: el backend espera a que PostgreSQL responda `pg_isready`; el worker y el frontend esperan a que el backend responda `/health`. |
| Olvidar aplicar migraciones o sembrar roles y admin. | El comando del backend hace `alembic upgrade head` → `seed_rbac` → `uvicorn` automáticamente (idempotente). |
| Perder los datos al reinstalar o reiniciar. | **Volúmenes con nombre** (`ds_pgdata`, `ds_ml_artifacts`) persisten fuera del contenedor. |
| Problemas de CORS entre el frontend y la API. | nginx sirve la web y reenvía `/api/` al backend: **mismo origen**, sin CORS. |
| Dejar la BD de pruebas mezclada con la de desarrollo. | Es posible levantar un PostgreSQL de pruebas aislado (puerto 55432) sin afectar al real. |
| Montar un entorno limpio y borrarlo sin dejar residuos. | `down` / `down -v` elimina todo sin ensuciar el sistema operativo. |

### 10.3 Los cuatro servicios (`infra/docker-compose.yml`)

Proyecto `ds-predictive`, red privada `ds-net`.

| Servicio | Contenedor | Imagen | Puerto | Qué hace |
|----------|-----------|--------|--------|----------|
| `postgres` | `ds-postgres` | `postgres:16-alpine` | `${POSTGRES_PORT}:5432` (en este equipo 5433) | Base de datos. Volumen `pgdata`. Ejecuta `01-database.sql` (zona UTC) solo la primera vez. Healthcheck `pg_isready`. |
| `backend` | `ds-backend` | build de `backend/Dockerfile` (`python:3.12-slim`) | `8000` | Migra, siembra y sirve la API con `--reload` en desarrollo. Monta `../backend` (hot reload), `ml_artifacts` y `../data`. Healthcheck `GET /health`. |
| `worker` | `ds-worker` | **misma imagen** del backend | — | Ejecuta `python -m app.workers.main`. Comparte volúmenes con el backend para leer/escribir los modelos entrenados. |
| `frontend` | `ds-frontend` | build multi-etapa de `frontend/Dockerfile` | `${FRONTEND_PORT}:80` (5173) | Etapa 1 compila con Node (`npm ci` + `npm run build`); etapa 2 sirve el resultado con nginx y hace de proxy de `/api/`. La imagen final no contiene Node ni el código fuente. |

Detalles de diseño:
- **Backend y worker comparten imagen** (`ds-predictive-backend:dev`): se construye una vez, y garantiza que ambos usen exactamente el mismo código y librerías de ML.
- **Dockerfile del backend** optimizado por capas: primero copia solo `pyproject.toml` e instala dependencias (se cachea mientras no cambien), luego copia el código. Ejecuta como usuario no root (`appuser`, uid 1000).
- **Volumen `ml_artifacts`** compartido: el backend predice con los modelos que el worker entrena.
- **Configuración por variables de entorno** (`.env`, que no se versiona; `.env.example` es la plantilla). Dentro de Docker el backend usa `POSTGRES_HOST=postgres` (nombre del servicio en la red interna).
- **nginx** (`frontend/nginx.conf`): `/api/` → `http://backend:8000` (límite de subida 50 MB, timeout 120 s para cargas de Excel y predicciones), `/assets/` con caché de un año (los archivos llevan hash en el nombre) y *fallback* a `index.html` para que las rutas de React Router funcionen al recargar.

### 10.4 Por qué no microservicios ni Kubernetes

Es una decisión consciente (ADR-01): el equipo es de una persona. Docker Compose da lo que se necesita (reproducibilidad, aislamiento, orquestación local) sin el costo operativo de un clúster.

### 10.5 ¿Es obligatorio?

No. El sistema también puede correr **sin Docker** (opción C en `COMANDOS_LEVANTAR.txt`: PostgreSQL local, `uvicorn`, `npm run dev`). Docker es la vía recomendada por reproducibilidad. También es posible un modo mixto: solo PostgreSQL en Docker y el resto en local para depurar con comodidad.

---

## 11. Cómo levantar y operar el sistema

### Con Docker (recomendado)

```bash
# 1) Crear .env (una vez)
make env                      # copia .env.example → .env

# 2) Levantar todo (postgres + backend + worker + frontend)
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
#   equivale a: make up

# URLs
#   Frontend: http://localhost:5173
#   API:      http://localhost:8000      Documentación: http://localhost:8000/docs

# Logs / estado / detener
make logs        make ps        make down
```

> `make clean-db` borra los volúmenes (**destruye toda la BD y los modelos**). Úsese con extremo cuidado.

### Sin Docker (Windows/PowerShell)

1. PostgreSQL 16 en `localhost` (puede ser solo el contenedor `postgres`).
2. `cd backend` → `pip install -e .` → `python -m alembic upgrade head` → `python -m uvicorn app.main:app --reload --port 8000`.
3. Worker (opcional): `python -m app.workers.main`.
4. `cd frontend` → `npm install` → `npm run dev`.

### Comandos útiles del `Makefile`

| Comando | Qué hace |
|---------|----------|
| `make migrate` / `make downgrade` | Aplica / revierte migraciones en el contenedor |
| `make revision m="texto"` | Genera una migración automática |
| `make seed` | Siembra roles, permisos, admin y parámetros |
| `make seed-catalogos ARGS=--aplicar` | Importa catálogos desde `data/raw` |
| `make test` / `make test-docker` | Pruebas del backend (pytest) |
| `make frontend-test` / `make frontend-build` | Pruebas (vitest) y build del frontend |
| `make lint` / `make format` | Ruff |
| `make openapi` / `make openapi-check` | Regenera / verifica el contrato `docs/architecture/openapi.yaml` |

Las pruebas de integración deben apuntar a una BD aislada (`DATABASE_URL` al puerto 55432), nunca a la BD de desarrollo.

### Aviso sobre cambios de código

Con la imagen del backend el código está montado (hot reload). Pero el **frontend se compila dentro de la imagen**: tras cambiar código del frontend hay que reconstruir (`up -d --build`).

---

## 12. Mapa de la API

Prefijo: `/api/v1` (a través de nginx: `http://localhost:5173/api/...`). Documentación interactiva en `/docs`.

| Módulo | Endpoints principales |
|--------|----------------------|
| `auth` | `POST /auth/login`, `GET /auth/me` |
| `users` | `GET /users/roles`, listar/crear/editar usuarios, activar/desactivar |
| `rbac` | Matriz de permisos, alta de roles, activar/desactivar, pantallas |
| `etl` | `POST /etl/upload-excel`, listar lotes, detalle, `GET/PUT /etl/config` |
| `predictions` | `POST /predictions/demand` |
| `routes` | Planes de carga: generar, consultar vigente, enviar/aprobar/rechazar/despachar |
| `inventory` | Existencias, kardex, ajustes |
| `products` | CRUD con baja lógica, reactivar, ajustar stock |
| `catalog` | Categorías, proveedores, rutas (alta/edición/activar), equipos de ruta, diagnósticos de calidad |
| `employees` | CRUD de personal de ruta con baja lógica |
| `purchasing` | Sugerencias, crear/listar/consultar pedidos, enviar, cancelar, confirmar, recibir |
| `ml` | Métricas, modelos, solicitud de reentrenamiento, estado de jobs, configuración |
| `alerts` | Listar y reconocer alertas |
| `reports` | Ventas vs. proyección, rotación y quiebres, comisiones, exportación CSV/XLSX |
| `liquidaciones` | Precarga, guardar borrador, listar, detalle, cerrar, corregir, anular, configuración |
| `bitacora` | Consulta paginada de la auditoría |

Errores de negocio con código estable (por ejemplo `LOTE_DUPLICADO`, `STOCK_INSUFICIENTE`, `EQUIPO_NO_SUMA_100`, `ULTIMO_ADMIN`, `HISTORIAL_INSUFICIENTE`, `SIN_MODELO_PRODUCTIVO`), que el frontend traduce a mensajes claros.

El contrato formal está en `docs/architecture/openapi.yaml` (generado) y `openapi.contract.yaml`; el frontend genera sus tipos con `npm run gen:api`.

---

## 13. Decisiones arquitectónicas (ADR)

Resumen de las decisiones documentadas en `docs/architecture/00-especificacion.md`:

| ADR | Decisión |
|-----|----------|
| 01 | Monolito modular en capas + Worker separado |
| 02 | PostgreSQL como única fuente de verdad; artefactos ML en disco con hash registrado |
| 03 | Un solo modelo en producción por familia |
| 04 | Reentrenamiento asíncrono con tabla de jobs + Worker (sin broker) |
| 05 | RBAC por permisos granulares; JWT con roles y permisos |
| 06 | La carga de ruta pasa siempre por aprobación humana; nunca se despacha sola |
| 07 | El stock disponible prevalece sobre la demanda predicha |
| 08 | Umbral de MAPE configurable; alerta y reentrenamiento por degradación |
| 09 / 10 | ETL con dos formatos (tabular y ancho), reglas de duplicados y comisiones |
| 11 | Pipeline de demanda: modelo de 1 paso, rezagos, medias móviles, pronóstico recursivo, intervalo 95 % |
| 12 | Gobernanza ML y frontend: periodos de 7 días, degradación por N periodos |
| 13 | Administración de usuarios, reportes y alertas por rol |
| 14 | **Liquidación diaria** como fuente de datos tras el arranque; política de datos; demanda censurada |
| 15 | Bitácora de auditoría append-only |
| 16 | Productos con baja lógica y ajuste manual de stock con motivo |
| 17 | Nombres canónicos de rol |
| 18 | Catálogos y equipos de ruta (empleados ≠ usuarios; reparto con vigencia) |
| 19 | RBAC dinámico en base de datos (roles, matriz y pantallas editables) |

---

## 14. Estructura del repositorio

```
.
├── backend/                  API, servicios, ML, worker, migraciones, tests
│   ├── app/{api,services,repositories,domain,schemas,ml,workers,core,db}
│   ├── scripts/              train_model.py, export_openapi.py
│   ├── tests/{unit,integration,ml}
│   ├── Dockerfile  alembic.ini  pyproject.toml
├── frontend/                 SPA React
│   ├── src/{views,components,hooks,services,app,types,utils}
│   ├── Dockerfile  nginx.conf  package.json
├── infra/
│   ├── docker-compose.yml    Orquestación (postgres, backend, worker, frontend)
│   ├── nginx/default.conf
│   └── postgres/init/01-database.sql
├── data/{raw,staging,processed,rejected,reportes,plantillas}
├── ml_artifacts/{models,reports}     Modelos entrenados (también en volumen Docker)
├── docs/architecture/        Especificación, OpenAPI
├── Proyecto de Graduación PG2/       Excel originales de marzo 2025
├── Makefile                  Atajos
├── COMANDOS_LEVANTAR.txt     Guía rápida de arranque
└── .env.example              Plantilla de configuración
```

---

*Documento generado a partir del estado del repositorio al 2026-10-19. Para el detalle de contratos, casos de prueba y wireframes originales, ver `docs/architecture/00-especificacion.md`.*
