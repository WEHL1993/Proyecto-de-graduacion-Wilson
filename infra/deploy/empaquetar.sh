#!/usr/bin/env bash
# Empaqueta lo necesario para la VM: código (incluye cambios sin commit), respaldo de la BD
# local y el volumen de modelos ML. Se ejecuta en Git Bash desde la raíz del proyecto, con
# los contenedores locales (ds-postgres) levantados.
#   bash infra/deploy/empaquetar.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1   # evita que Git Bash reescriba rutas como /v en `docker run`

SALIDA=despliegue
mkdir -p "$SALIDA"

echo "1/3 Código..."
tar czf "$SALIDA/codigo.tgz" \
  --exclude=./.git --exclude=./.venv --exclude='*/.venv' --exclude='*/node_modules' \
  --exclude=./frontend/dist --exclude='*/__pycache__' --exclude='*.egg-info' \
  --exclude='*/.pytest_cache' --exclude='*/.ruff_cache' \
  --exclude=./backups --exclude=./despliegue --exclude=./ml_artifacts \
  --exclude=./backend/ml_artifacts --exclude=./backend/data \
  --exclude='./Proyecto de Graduación PG2' --exclude=./.playwright-mcp \
  --exclude='*.log' --exclude='*.err' --exclude=./.env --exclude=./backend/.env \
  .

echo "2/3 Base de datos (pg_dump)..."
docker exec ds-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$SALIDA/bd.dump"

echo "3/3 Modelos ML (volumen ds_ml_artifacts)..."
docker run --rm -v ds_ml_artifacts:/v:ro alpine tar czf - -C /v . > "$SALIDA/ml_artifacts.tgz"

ls -lh "$SALIDA"
