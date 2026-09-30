"""Persistencia de existencias (`inventario`) y movimientos (`kardex`)."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ReferenciaTipo, TipoMovimiento
from app.domain.models.catalog import Inventario, Kardex, Producto


def obtener_por_productos(
    db: Session, producto_ids: Iterable[uuid.UUID], *, bloquear: bool = False
) -> dict[uuid.UUID, Inventario]:
    """`producto_id -> Inventario`. Con `bloquear` toma `FOR UPDATE` en orden de `producto_id`
    (orden estable entre transacciones: evita interbloqueos)."""
    ids = set(producto_ids)
    if not ids:
        return {}
    stmt = (
        select(Inventario).where(Inventario.producto_id.in_(ids)).order_by(Inventario.producto_id)
    )
    if bloquear:
        stmt = stmt.with_for_update()
    return {inv.producto_id: inv for inv in db.scalars(stmt)}


def crear_existencia(db: Session, producto_id: uuid.UUID) -> Inventario:
    """Fila de inventario en 0 para un producto que aún no tenía existencia."""
    inv = Inventario(
        producto_id=producto_id, stock_actual=Decimal("0"), stock_reservado=Decimal("0")
    )
    db.add(inv)
    db.flush()
    return inv


def registrar_movimiento(
    db: Session,
    *,
    producto_id: uuid.UUID,
    tipo: TipoMovimiento,
    cantidad: Decimal,
    saldo_resultante: Decimal,
    referencia_tipo: ReferenciaTipo | None,
    referencia_id: uuid.UUID | None,
    usuario_id: uuid.UUID | None,
) -> Kardex:
    movimiento = Kardex(
        producto_id=producto_id,
        tipo_movimiento=tipo,
        cantidad=cantidad,
        saldo_resultante=saldo_resultante,
        referencia_tipo=referencia_tipo,
        referencia_id=referencia_id,
        usuario_id=usuario_id,
    )
    db.add(movimiento)
    db.flush()
    return movimiento


def listar_existencias(
    db: Session,
    *,
    producto_id: uuid.UUID | None,
    solo_bajo_minimo: bool,
    limit: int,
    offset: int,
) -> tuple[Sequence[tuple[Producto, Inventario | None]], int]:
    """Productos activos con su existencia (LEFT JOIN: sin fila de inventario = stock 0)."""
    filtros = [Producto.activo.is_(True)]
    if producto_id is not None:
        filtros.append(Producto.id == producto_id)
    if solo_bajo_minimo:
        disponible = func.coalesce(Inventario.stock_actual - Inventario.stock_reservado, 0)
        filtros.append(disponible < Producto.stock_minimo)

    base = select(Producto, Inventario).outerjoin(Inventario).where(*filtros)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    filas = db.execute(base.order_by(Producto.sku).limit(limit).offset(offset)).all()
    return [(p, inv) for p, inv in filas], total


def listar_kardex(
    db: Session,
    *,
    producto_id: uuid.UUID | None,
    tipo: TipoMovimiento | None,
    desde: datetime | None,
    hasta: datetime | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Kardex], int]:
    filtros = []
    if producto_id is not None:
        filtros.append(Kardex.producto_id == producto_id)
    if tipo is not None:
        filtros.append(Kardex.tipo_movimiento == tipo)
    if desde is not None:
        filtros.append(Kardex.fecha_movimiento >= desde)
    if hasta is not None:
        filtros.append(Kardex.fecha_movimiento <= hasta)

    total = db.scalar(select(func.count()).select_from(Kardex).where(*filtros)) or 0
    movimientos = db.scalars(
        select(Kardex)
        .where(*filtros)
        .order_by(Kardex.fecha_movimiento.desc(), Kardex.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return movimientos, total
