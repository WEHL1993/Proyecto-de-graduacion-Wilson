#!/usr/bin/env bash
# Respalda la BD y los modelos de la VM en ~/respaldo-<fecha>/ (antes de borrar los recursos).
# Se ejecuta en la VM:  bash infra/deploy/respaldar.sh
set -euo pipefail

DESTINO=~/respaldo-$(date +%Y%m%d_%H%M)
mkdir -p "$DESTINO"
docker exec ds-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DESTINO/bd.dump"
docker run --rm -v ds_ml_artifacts:/v:ro alpine tar czf - -C /v . > "$DESTINO/ml_artifacts.tgz"
ls -lh "$DESTINO"
