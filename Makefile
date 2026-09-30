# Atajos del proyecto — Sistema de Análisis Predictivo (DCS, S.A.)
# Ejecutar desde la raíz del repositorio. `make help` lista los comandos.

ifeq ($(OS),Windows_NT)
  # En Windows las recetas corren en PowerShell 7 (soporta `&&` y rutas con `/`).
  SHELL       := pwsh.exe
  .SHELLFLAGS := -NoProfile -Command
  VENV_PY     := .venv/Scripts/python.exe
  SYS_PY      ?= python
else
  VENV_PY     := .venv/bin/python
  SYS_PY      ?= python3
endif

COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
BACKEND := backend

.DEFAULT_GOAL := help
.PHONY: help env install up down logs ps migrate migrate-local downgrade revision \
        openapi openapi-check seed test test-docker lint format clean-db

help: ## Muestra esta ayuda
	@$(SYS_PY) -c "import re; [print(f'  make {m[0]:<15} {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open('Makefile', encoding='utf-8').read(), re.M)]"

env: ## Crea .env a partir de .env.example si no existe
	@$(SYS_PY) -c "import os, shutil; os.path.exists('.env') or (shutil.copy('.env.example', '.env'), print('.env creado'))"

install: ## Crea backend/.venv e instala dependencias (incluye dev)
	cd $(BACKEND) && $(SYS_PY) -m venv .venv && $(VENV_PY) -m pip install -U pip && $(VENV_PY) -m pip install -e ".[dev]"

# ---------------------------------------------------------------- Docker
up: env ## Levanta postgres + backend (build incluido)
	$(COMPOSE) up -d --build

down: ## Detiene los contenedores (conserva volúmenes)
	$(COMPOSE) down

logs: ## Sigue los logs de todos los servicios
	$(COMPOSE) logs -f

ps: ## Estado de los servicios
	$(COMPOSE) ps

clean-db: ## DESTRUCTIVO: detiene todo y elimina volúmenes (pgdata, ml_artifacts)
	$(COMPOSE) down -v

# ---------------------------------------------------------------- Base de datos
migrate: ## Aplica migraciones Alembic dentro del contenedor backend
	$(COMPOSE) exec backend alembic upgrade head

migrate-local: ## Aplica migraciones desde el venv local (usa .env, postgres en localhost)
	cd $(BACKEND) && $(VENV_PY) -m alembic upgrade head

downgrade: ## Revierte la última migración (contenedor)
	$(COMPOSE) exec backend alembic downgrade -1

revision: ## Nueva migración autogenerada: make revision m="descripcion"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------- Contrato
openapi: ## Exporta el esquema de FastAPI a docs/architecture/openapi.yaml
	cd $(BACKEND) && $(VENV_PY) scripts/export_openapi.py

openapi-check: ## Falla si docs/architecture/openapi.yaml está desactualizado
	cd $(BACKEND) && $(VENV_PY) scripts/export_openapi.py --check

seed: ## Aplica seeds de roles, permisos, usuario admin y parametros_sistema
	cd $(BACKEND) && $(VENV_PY) -m app.db.seeds.seed_rbac

# ---------------------------------------------------------------- Calidad
test: ## Ejecuta pytest con el venv local
	cd $(BACKEND) && $(VENV_PY) -m pytest

test-docker: ## Ejecuta pytest dentro del contenedor backend
	$(COMPOSE) exec backend pytest

lint: ## Ruff (lint + formato en modo verificación)
	cd $(BACKEND) && $(VENV_PY) -m ruff check app scripts tests && $(VENV_PY) -m ruff format --check app scripts tests

format: ## Aplica formato y autocorrecciones de Ruff
	cd $(BACKEND) && $(VENV_PY) -m ruff check --fix app scripts tests && $(VENV_PY) -m ruff format app scripts tests
