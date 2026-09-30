"""Persistencia del agregado de pedidos a proveedor (`pedidos_proveedor` + `detalle_pedidos`)."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import EstadoPedido
from app.domain.models.catalog import Inventario, Producto, Proveedor
from app.domain.models.operations import DetallePedido, PedidoProveedor


def obtener(db: Session, pedido_id: uuid.UUID, *, bloquear: bool = False) -> PedidoProveedor | None:
    """Pedido con sus detalles. Con `bloquear` toma `FOR UPDATE` sobre la cabecera."""
    stmt = (
        select(PedidoProveedor)
        .where(PedidoProveedor.id == pedido_id)
        .options(selectinload(PedidoProveedor.detalles))
    )
    if bloquear:
        stmt = stmt.with_for_update(of=PedidoProveedor)
    return db.execute(stmt).scalar_one_or_none()


def listar(
    db: Session,
    *,
    proveedor_id: uuid.UUID | None,
    estado: EstadoPedido | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[PedidoProveedor], int]:
    filtros = []
    if proveedor_id is not None:
        filtros.append(PedidoProveedor.proveedor_id == proveedor_id)
    if estado is not None:
        filtros.append(PedidoProveedor.estado == estado)
    total = db.scalar(select(func.count()).select_from(PedidoProveedor).where(*filtros)) or 0
    pedidos = db.scalars(
        select(PedidoProveedor)
        .where(*filtros)
        .options(selectinload(PedidoProveedor.detalles))
        .order_by(PedidoProveedor.creado_en.desc(), PedidoProveedor.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return pedidos, total


def crear(
    db: Session, *, cabecera: dict[str, Any], detalles: Sequence[dict[str, Any]]
) -> PedidoProveedor:
    pedido = PedidoProveedor(**cabecera, detalles=[DetallePedido(**d) for d in detalles])
    db.add(pedido)
    db.flush()
    return pedido


def obtener_proveedor(db: Session, proveedor_id: uuid.UUID) -> Proveedor | None:
    return db.get(Proveedor, proveedor_id)


def nombres_proveedores(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    filas = db.execute(select(Proveedor.id, Proveedor.nombre).where(Proveedor.id.in_(ids)))
    return {pid: nombre for pid, nombre in filas}


def productos_de(db: Session, producto_ids: set[uuid.UUID]) -> dict[uuid.UUID, Producto]:
    if not producto_ids:
        return {}
    return {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(producto_ids)))}


def productos_reabastecibles(
    db: Session,
) -> Sequence[tuple[Producto, Proveedor, Inventario | None]]:
    """Productos activos con proveedor activo, con su existencia (sin fila = stock 0)."""
    stmt = (
        select(Producto, Proveedor, Inventario)
        .join(Proveedor, Producto.proveedor_id == Proveedor.id)
        .outerjoin(Inventario, Inventario.producto_id == Producto.id)
        .where(Producto.activo.is_(True), Proveedor.activo.is_(True))
        .order_by(Proveedor.nombre, Producto.sku)
    )
    return [(p, prov, inv) for p, prov, inv in db.execute(stmt).all()]
