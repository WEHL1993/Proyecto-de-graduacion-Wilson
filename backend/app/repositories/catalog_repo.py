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
