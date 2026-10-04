"""Consultas de catálogo para los filtros del frontend."""

from sqlalchemy.orm import Session

from app.repositories import catalog_repo, product_repo
from app.schemas.catalog import CategoriaItem, ProveedorItem, RouteItem
from app.services.bitacora_service import auditar


@auditar
def listar_rutas(db: Session) -> list[RouteItem]:
    return [
        RouteItem(id=r.id, codigo=r.codigo, nombre=r.nombre, zona=r.zona)
        for r in catalog_repo.listar_rutas_activas(db)
    ]


@auditar
def listar_categorias(db: Session) -> list[CategoriaItem]:
    return [CategoriaItem(id=c.id, nombre=c.nombre) for c in product_repo.listar_categorias(db)]


@auditar
def listar_proveedores(db: Session) -> list[ProveedorItem]:
    return [
        ProveedorItem(id=p.id, nombre=p.nombre) for p in product_repo.listar_proveedores_activos(db)
    ]
