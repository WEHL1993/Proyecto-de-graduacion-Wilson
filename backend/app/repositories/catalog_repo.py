"""Consultas de catálogo usadas por el ETL: mapeo de SKUs y códigos de ruta a sus ids."""

import uuid
from collections.abc import Iterable
from typing import NamedTuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.models.catalog import Producto, Ruta


class RutaResuelta(NamedTuple):
    id: uuid.UUID
    vendedor_id: uuid.UUID | None


def mapear_skus(db: Session, skus: Iterable[str]) -> dict[str, uuid.UUID]:
    """`SKU en mayúsculas -> productos.id` (comparación insensible a mayúsculas)."""
    claves = {s.strip().upper() for s in skus}
    if not claves:
        return {}
    stmt = select(func.upper(Producto.sku), Producto.id).where(func.upper(Producto.sku).in_(claves))
    return {sku: producto_id for sku, producto_id in db.execute(stmt)}


def mapear_rutas(db: Session, claves: Iterable[str]) -> dict[str, RutaResuelta]:
    """`clave en minúsculas -> ruta`; una ruta se resuelve por su `codigo` o por su `nombre`.

    Los Excel comerciales identifican la ruta por el nombre de la hoja (p. ej. «Cornelio»).
    """
    buscadas = {c.strip().lower() for c in claves}
    if not buscadas:
        return {}
    stmt = select(Ruta.id, Ruta.vendedor_id, Ruta.codigo, Ruta.nombre).where(
        or_(func.lower(Ruta.codigo).in_(buscadas), func.lower(Ruta.nombre).in_(buscadas))
    )
    resueltas: dict[str, RutaResuelta] = {}
    for ruta_id, vendedor_id, codigo, nombre in db.execute(stmt):
        for clave in (codigo.lower(), nombre.lower()):
            if clave in buscadas:
                resueltas.setdefault(clave, RutaResuelta(ruta_id, vendedor_id))
    return resueltas


def productos_existentes(db: Session, producto_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Subconjunto de `producto_ids` que existe en el catálogo."""
    ids = set(producto_ids)
    if not ids:
        return set()
    return set(db.scalars(select(Producto.id).where(Producto.id.in_(ids))))


def skus_de(db: Session, producto_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """`producto_id -> sku`."""
    ids = set(producto_ids)
    if not ids:
        return {}
    return {
        pid: sku
        for pid, sku in db.execute(select(Producto.id, Producto.sku).where(Producto.id.in_(ids)))
    }


def ruta_existe(db: Session, ruta_id: uuid.UUID) -> bool:
    return db.scalar(select(Ruta.id).where(Ruta.id == ruta_id)) is not None


def productos_resumen(
    db: Session, producto_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str]]:
    """`producto_id -> (sku, nombre)`."""
    ids = set(producto_ids)
    if not ids:
        return {}
    stmt = select(Producto.id, Producto.sku, Producto.nombre).where(Producto.id.in_(ids))
    return {pid: (sku, nombre) for pid, sku, nombre in db.execute(stmt)}


def listar_rutas_activas(db: Session) -> list[Ruta]:
    return list(db.scalars(select(Ruta).where(Ruta.activa.is_(True)).order_by(Ruta.codigo)))
