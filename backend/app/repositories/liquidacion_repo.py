"""Persistencia del agregado de liquidaciones diarias (`liquidaciones_diarias` + detalles)."""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import EstadoLiquidacion
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Ruta
from app.domain.models.sales import LiquidacionDetalle, LiquidacionDiaria


def obtener(
    db: Session, liquidacion_id: uuid.UUID, *, bloquear: bool = False
) -> LiquidacionDiaria | None:
    """Liquidación con sus líneas. Con `bloquear` toma `FOR UPDATE` sobre la cabecera."""
    stmt = (
        select(LiquidacionDiaria)
        .where(LiquidacionDiaria.id == liquidacion_id)
        .options(selectinload(LiquidacionDiaria.detalles))
    )
    if bloquear:
        stmt = stmt.with_for_update(of=LiquidacionDiaria)
    return db.execute(stmt).scalar_one_or_none()


def vigente(
    db: Session, fecha: date, ruta_id: uuid.UUID, vendedor_id: uuid.UUID | None = None
) -> LiquidacionDiaria | None:
    """Liquidación no anulada de la fecha/ruta (y vendedor, si se indica)."""
    stmt = (
        select(LiquidacionDiaria)
        .where(
            LiquidacionDiaria.fecha == fecha,
            LiquidacionDiaria.ruta_id == ruta_id,
            LiquidacionDiaria.estado != EstadoLiquidacion.ANULADA,
        )
        .options(selectinload(LiquidacionDiaria.detalles))
    )
    if vendedor_id is not None:
        stmt = stmt.where(LiquidacionDiaria.vendedor_id == vendedor_id)
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def crear(
    db: Session, *, cabecera: dict[str, Any], detalles: Sequence[dict[str, Any]]
) -> LiquidacionDiaria:
    """Inserta cabecera y líneas. Lanza `IntegrityError` si ya hay una liquidación vigente."""
    liquidacion = LiquidacionDiaria(
        **cabecera, detalles=[LiquidacionDetalle(**d) for d in detalles]
    )
    db.add(liquidacion)
    db.flush()
    return liquidacion


def reemplazar_lineas(
    db: Session, liquidacion: LiquidacionDiaria, detalles: Sequence[dict[str, Any]]
) -> None:
    """Sustituye las líneas (delete-orphan). Se vacía y se hace flush antes de insertar para no
    chocar con la restricción única `(liquidacion_id, producto_id)`."""
    liquidacion.detalles.clear()
    db.flush()
    liquidacion.detalles.extend(LiquidacionDetalle(**d) for d in detalles)
    db.flush()


def listar(
    db: Session,
    *,
    desde: date | None,
    hasta: date | None,
    ruta_id: uuid.UUID | None,
    vendedor_id: uuid.UUID | None,
    estado: EstadoLiquidacion | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[LiquidacionDiaria, str, str, Decimal]], int]:
    """`(cabecera, ruta, vendedor, unidades_vendidas)` más recientes primero, y el total."""
    filtros = []
    if desde is not None:
        filtros.append(LiquidacionDiaria.fecha >= desde)
    if hasta is not None:
        filtros.append(LiquidacionDiaria.fecha <= hasta)
    if ruta_id is not None:
        filtros.append(LiquidacionDiaria.ruta_id == ruta_id)
    if vendedor_id is not None:
        filtros.append(LiquidacionDiaria.vendedor_id == vendedor_id)
    if estado is not None:
        filtros.append(LiquidacionDiaria.estado == estado)

    total = db.scalar(select(func.count()).select_from(LiquidacionDiaria).where(*filtros)) or 0
    unidades = (
        select(func.coalesce(func.sum(LiquidacionDetalle.cantidad_vendida), 0))
        .where(LiquidacionDetalle.liquidacion_id == LiquidacionDiaria.id)
        .correlate(LiquidacionDiaria)
        .scalar_subquery()
    )
    filas = db.execute(
        select(LiquidacionDiaria, Ruta.nombre, Usuario.nombre_completo, unidades)
        .join(Ruta, Ruta.id == LiquidacionDiaria.ruta_id)
        .join(Usuario, Usuario.id == LiquidacionDiaria.vendedor_id)
        .where(*filtros)
        .order_by(LiquidacionDiaria.fecha.desc(), Ruta.nombre, LiquidacionDiaria.creado_en.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(liq, ruta, vendedor, Decimal(u)) for liq, ruta, vendedor, u in filas], total


# ------------------------------------------------------------------ insumos del entrenamiento
def rangos_cerrados_por_ruta(db: Session) -> dict[uuid.UUID, tuple[date, date]]:
    """Rango `(primer, último)` día liquidado (cerrado) de cada ruta."""
    stmt = (
        select(
            LiquidacionDiaria.ruta_id,
            func.min(LiquidacionDiaria.fecha),
            func.max(LiquidacionDiaria.fecha),
        )
        .where(LiquidacionDiaria.estado == EstadoLiquidacion.CERRADA)
        .group_by(LiquidacionDiaria.ruta_id)
    )
    return {ruta: (desde, hasta) for ruta, desde, hasta in db.execute(stmt)}


def dias_cerrados(db: Session) -> int:
    """Días calendario distintos con alguna liquidación cerrada."""
    return (
        db.scalar(
            select(func.count(func.distinct(LiquidacionDiaria.fecha))).where(
                LiquidacionDiaria.estado == EstadoLiquidacion.CERRADA
            )
        )
        or 0
    )


def censuras(db: Session) -> set[tuple[date, uuid.UUID, uuid.UUID]]:
    """`(fecha, producto_id, ruta_id)` de las líneas cerradas marcadas `agotado`."""
    stmt = (
        select(LiquidacionDiaria.fecha, LiquidacionDetalle.producto_id, LiquidacionDiaria.ruta_id)
        .join(LiquidacionDetalle, LiquidacionDetalle.liquidacion_id == LiquidacionDiaria.id)
        .where(
            LiquidacionDiaria.estado == EstadoLiquidacion.CERRADA,
            LiquidacionDetalle.agotado.is_(True),
        )
    )
    return {(f, p, r) for f, p, r in db.execute(stmt)}
