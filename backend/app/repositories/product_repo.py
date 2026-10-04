"""Persistencia del agregado `Producto` (CRUD administrativo con baja lógica, ADR-16)."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.enums import ESTADOS_CARGA_VIGENTE
from app.domain.models.catalog import Categoria, Inventario, Producto, Proveedor
from app.domain.models.operations import CargaRuta, DetalleCarga


def obtener(db: Session, producto_id: uuid.UUID, *, bloquear: bool = False) -> Producto | None:
    stmt = select(Producto).where(Producto.id == producto_id)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).one_or_none()


def obtener_por_sku(db: Session, sku: str) -> Producto | None:
    """Búsqueda insensible a mayúsculas (los SKU se guardan normalizados en mayúsculas)."""
    return db.scalars(select(Producto).where(func.upper(Producto.sku) == sku.upper())).first()


def existencia_de(
    db: Session, producto_id: uuid.UUID, *, bloquear: bool = False
) -> Inventario | None:
    stmt = select(Inventario).where(Inventario.producto_id == producto_id)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).first()


def categoria_existe(db: Session, categoria_id: uuid.UUID) -> bool:
    return db.scalar(select(Categoria.id).where(Categoria.id == categoria_id)) is not None


def nombre_de_categorias(db: Session, categoria_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not categoria_ids:
        return {}
    stmt = select(Categoria.id, Categoria.nombre).where(Categoria.id.in_(categoria_ids))
    return {cid: nombre for cid, nombre in db.execute(stmt)}


def proveedor_existe(db: Session, proveedor_id: uuid.UUID) -> bool:
    return db.scalar(select(Proveedor.id).where(Proveedor.id == proveedor_id)) is not None


def listar_categorias(db: Session) -> Sequence[Categoria]:
    return db.scalars(select(Categoria).order_by(Categoria.nombre)).all()


def listar_proveedores_activos(db: Session) -> Sequence[Proveedor]:
    return db.scalars(
        select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre)
    ).all()


def crear(db: Session, campos: dict[str, Any]) -> Producto:
    """Inserta el producto y su fila de `inventario` en 0 (misma transacción)."""
    producto = Producto(**campos)
    db.add(producto)
    db.flush()
    db.add(Inventario(producto_id=producto.id))
    db.flush()
    return producto


def listar(
    db: Session,
    *,
    activo: bool | None,
    categoria_id: uuid.UUID | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[tuple[Producto, Inventario | None]], int]:
    filtros = []
    if activo is not None:
        filtros.append(Producto.activo.is_(activo))
    if categoria_id is not None:
        filtros.append(Producto.categoria_id == categoria_id)
    if q:
        patron = f"%{q.strip()}%"
        filtros.append(or_(Producto.sku.ilike(patron), Producto.nombre.ilike(patron)))

    base = select(Producto, Inventario).outerjoin(Inventario).where(*filtros)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    filas = db.execute(base.order_by(Producto.sku).limit(limit).offset(offset)).all()
    return [(p, inv) for p, inv in filas], total


def cargas_vigentes_con(db: Session, producto_id: uuid.UUID) -> Sequence[uuid.UUID]:
    """Ids de cargas de ruta vigentes (borrador / pendiente / aprobada) que incluyen el producto."""
    stmt = (
        select(CargaRuta.id)
        .join(DetalleCarga, DetalleCarga.carga_id == CargaRuta.id)
        .where(DetalleCarga.producto_id == producto_id, CargaRuta.estado.in_(ESTADOS_CARGA_VIGENTE))
        .order_by(CargaRuta.id)
    )
    return db.scalars(stmt).all()


def inactivos_entre(db: Session, producto_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Subconjunto de `producto_ids` con `activo = false`."""
    if not producto_ids:
        return set()
    return set(
        db.scalars(
            select(Producto.id).where(Producto.id.in_(producto_ids), Producto.activo.is_(False))
        )
    )
