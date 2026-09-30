"""Consultas de catálogo para los filtros del frontend."""

from sqlalchemy.orm import Session

from app.repositories import catalog_repo
from app.schemas.catalog import RouteItem


def listar_rutas(db: Session) -> list[RouteItem]:
    return [
        RouteItem(id=r.id, codigo=r.codigo, nombre=r.nombre, zona=r.zona)
        for r in catalog_repo.listar_rutas_activas(db)
    ]
