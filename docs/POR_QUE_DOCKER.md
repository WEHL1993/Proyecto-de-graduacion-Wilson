# ¿Por qué se usa Docker en este proyecto?

Documento explicativo del uso de Docker en el **Sistema de Análisis Predictivo basado en Machine Learning**
(Desarrollos Comerciales del Sur, S.A.). Los archivos citados son los reales del repositorio:
`infra/docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` y `frontend/nginx.conf`.

---

## 1. Resumen

El sistema no es una sola aplicación: son **cuatro piezas** que deben funcionar juntas y con **versiones*
exactas de software:

| Pieza | Tecnología | Contenedor |
|---|---|---|
| Base de datos | PostgreSQL 16 | `ds-postgres` |
| API REST | Python 3.12 · FastAPI · scikit-learn · XGBoost | `ds-backend` (puerto 8000) |
| Worker predictivo | El mismo código del backend (`python -m app.workers.main`) | `ds-worker` |
| Interfaz web | React 19 compilado y servido por nginx | `ds-frontend` (puerto 5173) |

Docker permite levantar todo con **un solo comando** (`make up`) y obtener el **mismo resultado en
cualquier computadora**, sin instalar PostgreSQL, Python, Node ni dependencias de ML a mano.

---

## 2. Razones principales

### 2.1. Reproducibilidad: "en mi máquina funciona" deja de ser un problema

El proyecto depende de versiones concretas:

- Python **3.12** (el `pyproject.toml` exige `>=3.11`).
- PostgreSQL **16** (se usan `gen_random_uuid()`, índices únicos parciales, triggers, `CHECK`, etc.).
- Node 22 para compilar el frontend.
- Librerías de ML (pandas, scikit-learn, XGBoost) cuyos resultados pueden variar entre versiones.

Con Docker, estas versiones quedan **fijadas en código** (`FROM python:3.12-slim`,
`image: postgres:16-alpine`, `FROM node:22-alpine`). Quien clone el repositorio (el tesista, el asesor,
el jurado evaluador) ejecuta exactamente el mismo entorno. Esto es especialmente importante en una
**tesis**, donde los resultados deben poder reproducirse y verificarse.

### 2.2. Dependencias nativas difíciles de instalar (sobre todo en Windows)

XGBoost necesita el runtime de OpenMP (`libgomp1`) a nivel de sistema operativo. El `backend/Dockerfile`
lo instala una sola vez:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl
```

En un equipo Windows esto suele dar errores de compilación o de DLL faltantes. Dentro del contenedor
(Linux) está resuelto y probado.

### 2.3. Un solo comando para levantar un sistema de varias piezas

Sin Docker habría que: instalar PostgreSQL, crear usuario y base, crear el entorno virtual de Python,
instalar dependencias, ejecutar migraciones, cargar seeds, arrancar la API, arrancar el Worker, instalar
Node, compilar el frontend y servirlo. Con Docker Compose:

```bash
make up
# equivale a: docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

El contenedor `backend` ejecuta automáticamente, en orden:

```
alembic upgrade head            → crea/actualiza las tablas
python -m app.db.seeds.seed_rbac → roles, permisos, admin inicial y parámetros
uvicorn app.main:app ...         → inicia la API
```

### 2.4. Orquestación y orden de arranque

`docker-compose.yml` declara dependencias con *healthchecks*, de modo que cada servicio espera a que el
anterior esté realmente listo:

```
postgres (healthy)  →  backend (healthy)  →  worker
                                           →  frontend
```

- El backend no arranca hasta que PostgreSQL responde (`pg_isready`).
- El worker y el frontend no arrancan hasta que `/health` del backend responde.
- `restart: unless-stopped` reinicia los servicios si fallan. Esto cumple el requisito de que **un fallo
  del Worker no detenga el sistema** (ADR-04).

### 2.5. Red interna aislada y sin problemas de CORS

Los contenedores comparten la red `ds-net`. Se comunican por **nombre de servicio**
(`POSTGRES_HOST: postgres`, `proxy_pass http://backend:8000`), sin depender de IPs ni de `localhost`.

El frontend usa **nginx como proxy inverso**: el navegador solo habla con `localhost:5173`, y nginx
reenvía `/api/` al backend. Así el navegador ve un único origen y **no hay problemas de CORS**
(ver `frontend/nginx.conf`). Además `client_max_body_size 50m` permite subir los Excel del ETL.

### 2.6. Persistencia de datos mediante volúmenes

Los datos importantes viven en **volúmenes con nombre**, independientes del ciclo de vida de los
contenedores:

| Volumen | Contenido |
|---|---|
| `ds_pgdata` | Base de datos PostgreSQL |
| `ds_ml_artifacts` | Modelos entrenados (artefactos del registro ML) |

Se puede destruir y recrear un contenedor (por ejemplo al actualizar código) sin perder datos ni modelos.
Solo `make clean-db` borra los volúmenes, y por eso está documentado como **destructivo**.

Además se monta `../data:/app/data` para que el ETL lea los Excel originales de `data/raw/`.

### 2.7. Un mismo código, dos procesos (API y Worker)

El backend y el worker usan **la misma imagen** (`ds-predictive-backend:dev`) con comandos distintos:

- `backend` → `uvicorn app.main:app`
- `worker` → `python -m app.workers.main`

Esto garantiza que ambos ejecutan exactamente el mismo código, modelos y reglas de negocio, y evita
mantener dos entornos distintos.

### 2.8. Desarrollo cómodo con *hot reload*

En `docker-compose.yml` el código se **monta sobre la imagen** (`../backend:/app`) y uvicorn corre con
`--reload`. Al editar un archivo Python en el editor, la API se reinicia sola dentro del contenedor, sin
reconstruir la imagen.

### 2.9. Imágenes optimizadas y más seguras

- **Frontend con build multi-etapa:** la etapa `node:22-alpine` compila la SPA; la imagen final es solo
  `nginx:1.27-alpine` con los archivos estáticos. No se incluye Node ni `node_modules` en producción, lo que
  da una imagen pequeña.
- **Caché de capas:** en el backend las dependencias se instalan en una capa propia que solo se reconstruye
  si cambia `pyproject.toml`, acelerando los *builds*.
- **Usuario sin privilegios:** el backend corre como `appuser` (uid 1000), no como `root`.
- **Imágenes ligeras:** `slim` y `alpine` reducen tamaño y superficie de ataque.

### 2.10. Entorno aislado que no ensucia el equipo

Todo queda encapsulado: no se instala PostgreSQL ni librerías globales en el computador, no hay conflictos
con otros proyectos que usen otra versión de Python o de Postgres, y limpiar es tan simple como
`make down`.

### 2.11. Camino directo hacia el despliegue

Las imágenes construidas son la unidad de despliegue. Si la empresa o la universidad llevara el prototipo a
un servidor, bastaría con instalar Docker y reutilizar el mismo `docker-compose.yml` (cambiando variables
como `JWT_SECRET_KEY`, `ENVIRONMENT` y las credenciales de la base de datos mediante `.env`).

---

## 3. ¿Qué pasaría sin Docker?

| Aspecto | Con Docker | Sin Docker |
|---|---|---|
| Puesta en marcha | `make up` | Instalar y configurar 4+ componentes manualmente |
| Versión de PostgreSQL | Fija (16) | Depende de lo instalado en la máquina |
| Dependencias nativas de ML | Resueltas en la imagen | Posibles errores (OpenMP, compiladores) |
| Reproducibilidad de la tesis | Alta | Baja |
| Orden de arranque y reinicios | Automático (healthchecks) | Manual |
| Limpieza | `make down` | Desinstalar servicios y entornos |

---

## 4. Uso práctico

```bash
make env     # crea .env desde .env.example (primera vez)
make up      # levanta postgres + backend (+ worker y frontend con el compose completo)
make down    # detiene los servicios
```

Stack completo:

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

Puntos de acceso:

| Servicio | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API / Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| PostgreSQL | `localhost:5432` |

> **Nota:** Docker **no es obligatorio** para desarrollar. También se puede trabajar en local con
> `backend/.venv` (`make install`, `make migrate-local`, `make test`) apuntando a un PostgreSQL en
> `localhost:5432`. Docker es la forma recomendada porque garantiza un entorno idéntico para todos.

---

## 5. Conclusión

Docker se usa porque el sistema es **multiservicio** (base de datos, API, worker y frontend), requiere
**versiones exactas** de software y **dependencias nativas** de Machine Learning, y porque, al ser un
prototipo académico, necesita ser **reproducible, portable y fácil de levantar** por terceros. Docker
Compose resuelve todo esto de forma declarativa y versionada junto con el código.
