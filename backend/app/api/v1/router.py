"""Router raíz de la API v1. Cada módulo (auth, etl, predictions, routes, ml...) se
registra aquí a medida que se implementa, conforme a docs/architecture/openapi.contract.yaml."""

from fastapi import APIRouter

from app.api.v1 import auth, etl

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(etl.router)
