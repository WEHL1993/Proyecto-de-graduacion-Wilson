#!/usr/bin/env bash
# Instala o actualiza el sistema en la VM. Se ejecuta en la VM desde la raíz del proyecto:
#   bash infra/deploy/instalar.sh <dominio>.cloudapp.azure.com
# La primera vez instala Docker, genera .env.prod con secretos aleatorios y restaura
# ~/bd.dump y ~/ml_artifacts.tgz si la BD y el volumen están vacíos.
set -euo pipefail

DOMINIO="${1:?Uso: bash infra/deploy/instalar.sh <dominio>.cloudapp.azure.com}"
COMPOSE="docker compose -f infra/docker-compose.prod.yml --env-file .env.prod"
DOCKER="docker"

if ! command -v docker >/dev/null; then
  echo "Instalando Docker..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
# En la primera ejecución el grupo docker aún no aplica a esta sesión.
docker info >/dev/null 2>&1 || { DOCKER="sudo docker"; COMPOSE="sudo $COMPOSE"; }

if [ ! -f .env.prod ]; then
  cat > .env.prod <<EOF
DOMINIO=$DOMINIO
POSTGRES_USER=ds_user
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=ds_predictive
JWT_SECRET_KEY=$(openssl rand -hex 48)
JWT_EXPIRE_MINUTES=60
EOF
  chmod 600 .env.prod
  echo ".env.prod creado."
fi

$COMPOSE up -d postgres
until $DOCKER exec ds-postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  sleep 2
done

TABLAS="$($DOCKER exec ds-postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from information_schema.tables where table_schema = '\''public'\''"')"
if [ "$TABLAS" = "0" ] && [ -f ~/bd.dump ]; then
  echo "Restaurando ~/bd.dump..."
  $DOCKER exec -i ds-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' < ~/bd.dump
fi

$DOCKER volume create ds_ml_artifacts >/dev/null
if [ -f ~/ml_artifacts.tgz ] && [ -z "$($DOCKER run --rm -v ds_ml_artifacts:/v alpine ls -A /v)" ]; then
  echo "Restaurando ~/ml_artifacts.tgz..."
  $DOCKER run --rm -i -v ds_ml_artifacts:/v alpine sh -c 'tar xzf - -C /v && chown -R 1000:1000 /v' < ~/ml_artifacts.tgz
fi

# El backend corre como uid 1000 y escribe en data/ (staging, reportes).
sudo chown -R 1000:1000 data

$COMPOSE up -d --build
$COMPOSE ps
echo
echo "Listo: https://$DOMINIO"
