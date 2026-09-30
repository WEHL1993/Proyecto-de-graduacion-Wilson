"""Persistencia de alertas del sistema."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.domain.enums import EstadoAlerta, Severidad, TipoAlerta
from app.domain.models.ml import Alerta


def crear(
    db: Session,
    *,
    tipo: TipoAlerta,
    severidad: Severidad,
    mensaje: str,
    producto_id: uuid.UUID | None = None,
    modelo_id: uuid.UUID | None = None,
) -> Alerta:
    alerta = Alerta(
        tipo=tipo,
        severidad=severidad,
        mensaje=mensaje,
        producto_id=producto_id,
        modelo_id=modelo_id,
    )
    db.add(alerta)
    db.flush()
    return alerta


def abierta_de_producto(db: Session, *, tipo: TipoAlerta, producto_id: uuid.UUID) -> Alerta | None:
    """Alerta aún `abierta` del mismo tipo y producto (evita duplicar la bandeja)."""
    return db.scalars(
        select(Alerta)
        .where(
            Alerta.tipo == tipo,
            Alerta.producto_id == producto_id,
            Alerta.estado == EstadoAlerta.ABIERTA,
        )
        .limit(1)
    ).first()


def abierta_de_modelo(db: Session, *, tipo: TipoAlerta, modelo_id: uuid.UUID) -> Alerta | None:
    """Alerta aún `abierta` del mismo tipo y modelo (evita duplicar la bandeja)."""
    return db.scalars(
        select(Alerta)
        .where(
            Alerta.tipo == tipo,
            Alerta.modelo_id == modelo_id,
            Alerta.estado == EstadoAlerta.ABIERTA,
        )
        .limit(1)
    ).first()


def resolver_abiertas_de_modelo(db: Session, *, tipo: TipoAlerta, modelo_id: uuid.UUID) -> int:
    resultado = db.execute(
        update(Alerta)
        .where(
            Alerta.tipo == tipo,
            Alerta.modelo_id == modelo_id,
            Alerta.estado == EstadoAlerta.ABIERTA,
        )
        .values(estado=EstadoAlerta.RESUELTA, resuelta_en=datetime.now(UTC))
    )
    return resultado.rowcount


def listar(
    db: Session, *, estado: EstadoAlerta | None, limite: int
) -> tuple[Sequence[Alerta], int]:
    """Alertas (críticas primero, luego las más recientes) y el total que cumple el filtro."""
    filtro = [] if estado is None else [Alerta.estado == estado]
    total = db.scalar(select(func.count()).select_from(Alerta).where(*filtro)) or 0
    orden_severidad = case(
        {Severidad.CRITICA.value: 0, Severidad.ADVERTENCIA.value: 1},
        value=Alerta.severidad,
        else_=2,
    )
    filas = db.scalars(
        select(Alerta)
        .where(*filtro)
        .order_by(orden_severidad, Alerta.creada_en.desc())
        .limit(limite)
    ).all()
    return filas, total
