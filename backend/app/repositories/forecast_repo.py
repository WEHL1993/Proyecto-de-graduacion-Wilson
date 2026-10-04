"""Persistencia de `pronosticos_demanda`."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.enums import EstadoLiquidacion
from app.domain.models.ml import PronosticoDemanda
from app.domain.models.sales import LiquidacionDiaria, VentaHistorica

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
    db: Session,
    modelo_id: uuid.UUID,
    desde: date,
    hasta: date,
    *,
    ventas_hasta: date,
    ultima_fecha_excel: date | None = None,
) -> int:
    """Cruza los pronósticos del periodo con `ventas_historicas` y fija `demanda_real`.

    Solo toca fechas ya cubiertas por ventas (`<= ventas_hasta`): un día sin fila dentro de lo
    cargado es demanda 0. Un pronóstico agregado (`ruta_id` NULL) suma todas las rutas.

    ADR-14: pasada la línea base Excel (`ultima_fecha_excel`) un día solo cuenta para una ruta
    si esa ruta tiene liquidación cerrada ese día; sin liquidación no hay dato (no es 0).
    """
    liquidada = (
        exists()
        .where(
            LiquidacionDiaria.fecha == PronosticoDemanda.fecha_objetivo,
            LiquidacionDiaria.ruta_id == PronosticoDemanda.ruta_id,
            LiquidacionDiaria.estado == EstadoLiquidacion.CERRADA,
        )
        .correlate(PronosticoDemanda)
    )
    cubierto = or_(PronosticoDemanda.ruta_id.is_(None), liquidada)
    if ultima_fecha_excel is not None:
        cubierto = or_(cubierto, PronosticoDemanda.fecha_objetivo <= ultima_fecha_excel)

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
            cubierto,
        )
        .values(demanda_real=real)
    )
    return resultado.rowcount


def fijar_demanda_real_dia(
    db: Session,
    fecha: date,
    ruta_id: uuid.UUID,
    reales: Mapping[uuid.UUID, tuple[Decimal, bool]],
) -> int:
    """Liquidación cerrada: fija `demanda_real` (y su censura) de los pronósticos de esa
    fecha/ruta de todos los modelos, por producto. `reales`: `producto -> (vendido, agotado)`."""
    actualizados = 0
    for producto_id, (vendido, agotado) in reales.items():
        actualizados += db.execute(
            update(PronosticoDemanda)
            .where(
                PronosticoDemanda.fecha_objetivo == fecha,
                PronosticoDemanda.ruta_id == ruta_id,
                PronosticoDemanda.producto_id == producto_id,
            )
            .values(demanda_real=vendido, demanda_censurada=agotado)
        ).rowcount
    return actualizados


def limpiar_demanda_real_dia(
    db: Session, fecha: date, ruta_id: uuid.UUID, producto_ids: Sequence[uuid.UUID]
) -> int:
    """Anulación de una liquidación: su demanda real vuelve a ser desconocida."""
    if not producto_ids:
        return 0
    return db.execute(
        update(PronosticoDemanda)
        .where(
            PronosticoDemanda.fecha_objetivo == fecha,
            PronosticoDemanda.ruta_id == ruta_id,
            PronosticoDemanda.producto_id.in_(producto_ids),
        )
        .values(demanda_real=None, demanda_censurada=False)
    ).rowcount


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
    """`(producto_id, demanda_predicha, demanda_real)` de los pronósticos con real conocido.

    Excluye los censurados (ADR-14): con producto agotado la demanda real es solo un piso y su
    error no mide al modelo."""
    filas = db.execute(
        select(
            PronosticoDemanda.producto_id,
            PronosticoDemanda.demanda_predicha,
            PronosticoDemanda.demanda_real,
        ).where(
            PronosticoDemanda.modelo_id == modelo_id,
            PronosticoDemanda.fecha_objetivo.between(desde, hasta),
            PronosticoDemanda.demanda_real.is_not(None),
            PronosticoDemanda.demanda_censurada.is_(False),
        )
    )
    return [tuple(f) for f in filas]
