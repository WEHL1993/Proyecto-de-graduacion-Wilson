"""Persistencia de `pronosticos_demanda`."""

import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.models.ml import PronosticoDemanda
from app.domain.models.sales import VentaHistorica

_UQ_PRONOSTICO = "uq_pronosticos_demanda_clave"


def upsert_pronosticos(db: Session, filas: Sequence[dict[str, Any]]) -> int:
    """Idempotente por `(modelo, producto, ruta, fecha_objetivo, horizonte)`: un nuevo cálculo
    reemplaza predicción e intervalo y conserva `demanda_real` ya registrada."""
    if not filas:
        return 0
    stmt = pg_insert(PronosticoDemanda).values(list(filas))
    stmt = stmt.on_conflict_do_update(
        constraint=_UQ_PRONOSTICO,
        set_={
            "demanda_predicha": stmt.excluded.demanda_predicha,
            "limite_inferior": stmt.excluded.limite_inferior,
            "limite_superior": stmt.excluded.limite_superior,
            "generado_en": stmt.excluded.generado_en,
        },
    )
    db.execute(stmt)
    return len(filas)


def registrar_demanda_real(
    db: Session, modelo_id: uuid.UUID, desde: date, hasta: date, *, ventas_hasta: date
) -> int:
    """Cruza los pronósticos del periodo con `ventas_historicas` y fija `demanda_real`.

    Solo toca fechas ya cubiertas por ventas (`<= ventas_hasta`): un día sin fila dentro de lo
    cargado es demanda 0. Un pronóstico agregado (`ruta_id` NULL) suma todas las rutas.
    """
    real = (
        select(func.coalesce(func.sum(VentaHistorica.cantidad), 0))
        .where(
            VentaHistorica.fecha_venta == PronosticoDemanda.fecha_objetivo,
            VentaHistorica.producto_id == PronosticoDemanda.producto_id,
            or_(
                PronosticoDemanda.ruta_id.is_(None),
                VentaHistorica.ruta_id == PronosticoDemanda.ruta_id,
            ),
        )
        .correlate(PronosticoDemanda)
        .scalar_subquery()
    )
    resultado = db.execute(
        update(PronosticoDemanda)
        .where(
            PronosticoDemanda.modelo_id == modelo_id,
            PronosticoDemanda.fecha_objetivo.between(desde, min(hasta, ventas_hasta)),
        )
        .values(demanda_real=real)
    )
    return resultado.rowcount


def primera_fecha_objetivo(db: Session, modelo_id: uuid.UUID) -> date | None:
    return db.scalar(
        select(func.min(PronosticoDemanda.fecha_objetivo)).where(
            PronosticoDemanda.modelo_id == modelo_id
        )
    )


def ultima_fecha_con_real(db: Session, modelo_id: uuid.UUID) -> date | None:
    return db.scalar(
        select(func.max(PronosticoDemanda.fecha_objetivo)).where(
            PronosticoDemanda.modelo_id == modelo_id,
            PronosticoDemanda.demanda_real.is_not(None),
        )
    )


def evaluables(
    db: Session, modelo_id: uuid.UUID, desde: date, hasta: date
) -> list[tuple[uuid.UUID, Decimal, Decimal]]:
    """`(producto_id, demanda_predicha, demanda_real)` de los pronósticos con real conocido."""
    filas = db.execute(
        select(
            PronosticoDemanda.producto_id,
            PronosticoDemanda.demanda_predicha,
            PronosticoDemanda.demanda_real,
        ).where(
            PronosticoDemanda.modelo_id == modelo_id,
            PronosticoDemanda.fecha_objetivo.between(desde, hasta),
            PronosticoDemanda.demanda_real.is_not(None),
        )
    )
    return [tuple(f) for f in filas]
