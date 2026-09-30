"""Catálogos de apoyo al frontend (`GET /catalog/routes`)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.catalog import RouteItem
from app.services import catalog_service

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get(
    "/routes",
    response_model=list[RouteItem],
    summary="Rutas activas",
    description="Cualquier usuario autenticado. Alimenta el filtro de ruta del dashboard.",
)
def listar_rutas(db: DBSession, _usuario: CurrentUser) -> list[RouteItem]:
    return catalog_service.listar_rutas(db)
