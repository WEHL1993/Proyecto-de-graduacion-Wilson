"""Catálogos de apoyo al frontend (`GET /catalog/routes|categories|suppliers`)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.catalog import CategoriaItem, ProveedorItem, RouteItem
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


@router.get(
    "/categories",
    response_model=list[CategoriaItem],
    summary="Categorías de producto",
    description="Cualquier usuario autenticado. Alimenta el formulario de productos.",
)
def listar_categorias(db: DBSession, _usuario: CurrentUser) -> list[CategoriaItem]:
    return catalog_service.listar_categorias(db)


@router.get(
    "/suppliers",
    response_model=list[ProveedorItem],
    summary="Proveedores activos",
    description="Cualquier usuario autenticado. Alimenta el formulario de productos.",
)
def listar_proveedores(db: DBSession, _usuario: CurrentUser) -> list[ProveedorItem]:
    return catalog_service.listar_proveedores(db)
