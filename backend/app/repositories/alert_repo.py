"""Persistencia de alertas del sistema."""

import uuid

from sqlalchemy import select
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
