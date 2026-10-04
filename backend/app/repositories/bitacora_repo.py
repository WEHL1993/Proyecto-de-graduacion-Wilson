"""Consultas de la bitácora de auditoría (append-only: solo inserta y lee)."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models.bitacora import Bitacora


def insertar(db: Session, **campos: Any) -> Bitacora:
    registro = Bitacora(**campos)
    db.add(registro)
    db.flush()
    return registro


def listar(
    db: Session,
    *,
    desde: datetime | None,
    hasta: datetime | None,
    usuario_id: uuid.UUID | None,
    accion: str | None,
    origen: str | None,
    resultado: str | None,
    request_id: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Bitacora], int]:
    filtros = []
    if desde is not None:
        filtros.append(Bitacora.ocurrido_en >= desde)
    if hasta is not None:
        filtros.append(Bitacora.ocurrido_en <= hasta)
    if usuario_id is not None:
        filtros.append(Bitacora.usuario_id == usuario_id)
    if accion:
        filtros.append(Bitacora.accion.ilike(f"%{accion}%"))
    if origen:
        filtros.append(Bitacora.origen == origen)
    if resultado:
        filtros.append(Bitacora.resultado == resultado)
    if request_id:
        filtros.append(Bitacora.request_id == request_id)
    total = db.scalar(select(func.count()).select_from(Bitacora).where(*filtros)) or 0
    stmt = (
        select(Bitacora)
        .where(*filtros)
        .order_by(Bitacora.ocurrido_en.desc(), Bitacora.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all(), total
