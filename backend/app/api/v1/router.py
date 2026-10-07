"""Router raíz de la API v1. Cada módulo (auth, etl, predictions, routes, ml...) se
registra aquí a medida que se implementa, conforme a docs/architecture/openapi.contract.yaml."""

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    auth,
    bitacora,
    catalog,
    employees,
    etl,
    inventory,
    liquidaciones,
    ml,
    predictions,
    products,
    purchasing,
    reports,
    routes,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(etl.router)
api_router.include_router(predictions.router)
api_router.include_router(routes.router)
api_router.include_router(inventory.router)
api_router.include_router(products.router)
api_router.include_router(ml.router)
api_router.include_router(alerts.router)
api_router.include_router(catalog.router)
api_router.include_router(employees.router)
api_router.include_router(purchasing.router)
api_router.include_router(users.router)
api_router.include_router(reports.router)
api_router.include_router(liquidaciones.router)
api_router.include_router(bitacora.router)
