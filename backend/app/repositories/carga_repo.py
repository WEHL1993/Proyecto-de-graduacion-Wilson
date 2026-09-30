"""Persistencia del agregado de cargas de ruta (`cargas_ruta` + `detalle_cargas`)."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import ESTADOS_CARGA_VIGENTE
from app.domain.models.operations import CargaRuta, DetalleCarga


def obtener(db: Session, carga_id: uuid.UUID, *, bloquear: bool = False) -> CargaRuta | None:
    """Carga con sus detalles. Con `bloquear` toma `FOR UPDATE` sobre la cabecera."""
    stmt = (
        select(CargaRuta).where(CargaRuta.id == carga_id).options(selectinload(CargaRuta.detalles))
    )
    if bloquear:
        stmt = stmt.with_for_update(of=CargaRuta)
    return db.execute(stmt).scalar_one_or_none()


def vigente_de_ruta(db: Session, ruta_id: uuid.UUID, fecha_operacion: date) -> CargaRuta | None:
    return db.scalars(
        select(CargaRuta).where(
            CargaRuta.ruta_id == ruta_id,
            CargaRuta.fecha_operacion == fecha_operacion,
            CargaRuta.estado.in_(ESTADOS_CARGA_VIGENTE),
        )
    ).first()


def crear(
    db: Session, *, cabecera: dict[str, Any], detalles: Sequence[dict[str, Any]]
) -> CargaRuta:
    """Inserta cabecera y detalles. Lanza `IntegrityError` si ya hay una carga vigente."""
    carga = CargaRuta(**cabecera, detalles=[DetalleCarga(**d) for d in detalles])
    db.add(carga)
    db.flush()
    return carga
