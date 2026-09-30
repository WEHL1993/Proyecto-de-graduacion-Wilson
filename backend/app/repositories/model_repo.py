"""Consultas del agregado de modelos ML: `modelos_ml` y `metricas_evaluacion`."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import EstadoModelo
from app.domain.models.ml import MetricaEvaluacion, ModeloML


def obtener(db: Session, modelo_id: uuid.UUID, *, bloquear: bool = False) -> ModeloML | None:
    stmt = select(ModeloML).where(ModeloML.id == modelo_id)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def obtener_produccion(db: Session, nombre: str) -> ModeloML | None:
    """El único modelo en estado `produccion` de la familia `nombre` (ADR-03)."""
    return db.execute(
        select(ModeloML).where(
            ModeloML.nombre == nombre, ModeloML.estado == EstadoModelo.PRODUCCION
        )
    ).scalar_one_or_none()


def siguiente_version(db: Session, nombre: str) -> str:
    """`v1.0.N` con N = cantidad de versiones ya registradas de la familia + 1."""
    total = db.scalar(select(func.count()).select_from(ModeloML).where(ModeloML.nombre == nombre))
    return f"v1.0.{(total or 0) + 1}"


def crear(db: Session, **campos: Any) -> ModeloML:
    modelo = ModeloML(**campos)
    db.add(modelo)
    db.flush()
    return modelo


def registrar_metricas(db: Session, filas: Sequence[dict[str, Any]]) -> None:
    db.add_all(MetricaEvaluacion(**fila) for fila in filas)
    db.flush()


def archivar_produccion_de(db: Session, nombre: str, *, excepto: uuid.UUID) -> None:
    """Archiva los modelos en producción de la familia (bloqueados FOR UPDATE)."""
    vigentes = db.execute(
        select(ModeloML)
        .where(
            ModeloML.nombre == nombre,
            ModeloML.estado == EstadoModelo.PRODUCCION,
            ModeloML.id != excepto,
        )
        .with_for_update()
    ).scalars()
    for modelo in vigentes:
        modelo.estado = EstadoModelo.ARCHIVADO
    db.flush()  # libera el índice único parcial antes de promover el nuevo


def marcar_produccion(db: Session, modelo: ModeloML) -> None:
    modelo.estado = EstadoModelo.PRODUCCION
    modelo.promovido_en = datetime.now(UTC)
    db.flush()
