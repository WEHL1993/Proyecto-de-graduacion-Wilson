"""Persistencia administrativa del agregado `Ruta` (M02). Las consultas del ETL viven en
`catalog_repo`."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import ESTADOS_CARGA_VIGENTE, EstadoLiquidacion
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Ruta
from app.domain.models.operations import CargaRuta
from app.domain.models.sales import LiquidacionDiaria


def obtener(db: Session, ruta_id: uuid.UUID, *, bloquear: bool = False) -> Ruta | None:
    stmt = select(Ruta).where(Ruta.id == ruta_id)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).one_or_none()


def obtener_por_codigo(db: Session, codigo: str) -> Ruta | None:
    return db.scalars(select(Ruta).where(func.upper(Ruta.codigo) == codigo.upper())).first()


def listar(db: Session, *, activa: bool | None) -> Sequence[Ruta]:
    stmt = select(Ruta).order_by(Ruta.codigo)
    if activa is not None:
        stmt = stmt.where(Ruta.activa.is_(activa))
    return db.scalars(stmt).all()


def crear(db: Session, campos: dict[str, Any]) -> Ruta:
    ruta = Ruta(**campos)
    db.add(ruta)
    db.flush()
    return ruta


def usuario_existe(db: Session, usuario_id: uuid.UUID) -> bool:
    return db.scalar(select(Usuario.id).where(Usuario.id == usuario_id)) is not None


def liquidaciones_en_borrador(db: Session, ruta_id: uuid.UUID) -> Sequence[uuid.UUID]:
    stmt = select(LiquidacionDiaria.id).where(
        LiquidacionDiaria.ruta_id == ruta_id,
        LiquidacionDiaria.estado == EstadoLiquidacion.BORRADOR,
    )
    return db.scalars(stmt).all()


def cargas_vigentes(db: Session, ruta_id: uuid.UUID) -> Sequence[uuid.UUID]:
    stmt = select(CargaRuta.id).where(
        CargaRuta.ruta_id == ruta_id, CargaRuta.estado.in_(ESTADOS_CARGA_VIGENTE)
    )
    return db.scalars(stmt).all()
