"""Consultas del agregado de modelos ML: `modelos_ml` y `metricas_evaluacion`."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, func, select
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


def descartar(db: Session, modelo: ModeloML) -> None:
    modelo.estado = EstadoModelo.DESCARTADO
    db.flush()


def listar_de_familia(db: Session, nombre: str, *, limite: int = 20) -> Sequence[ModeloML]:
    """Modelos de la familia, del más reciente al más antiguo."""
    return db.scalars(
        select(ModeloML)
        .where(ModeloML.nombre == nombre)
        .order_by(ModeloML.entrenado_en.desc(), ModeloML.version.desc())
        .limit(limite)
    ).all()


# ------------------------------------------------------------------ metricas_evaluacion
def metricas(
    db: Session,
    modelo_id: uuid.UUID,
    tipo: str,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    producto_id: uuid.UUID | None = None,
    solo_globales: bool = False,
    solo_productos: bool = False,
) -> Sequence[MetricaEvaluacion]:
    """Métricas del modelo ordenadas por `periodo_hasta` ascendente.

    Sin `producto_id`: `solo_globales` (producto NULL) o `solo_productos` (producto no NULL).
    """
    stmt = select(MetricaEvaluacion).where(
        MetricaEvaluacion.modelo_id == modelo_id, MetricaEvaluacion.tipo_evaluacion == tipo
    )
    if desde is not None:
        stmt = stmt.where(MetricaEvaluacion.periodo_hasta >= desde)
    if hasta is not None:
        stmt = stmt.where(MetricaEvaluacion.periodo_hasta <= hasta)
    if producto_id is not None:
        stmt = stmt.where(MetricaEvaluacion.producto_id == producto_id)
    elif solo_globales:
        stmt = stmt.where(MetricaEvaluacion.producto_id.is_(None))
    elif solo_productos:
        stmt = stmt.where(MetricaEvaluacion.producto_id.is_not(None))
    stmt = stmt.order_by(MetricaEvaluacion.periodo_hasta, MetricaEvaluacion.evaluado_en)
    return db.scalars(stmt).all()


def ultimas_globales(
    db: Session, modelo_id: uuid.UUID, tipo: str, *, limite: int
) -> Sequence[MetricaEvaluacion]:
    """Últimas `limite` métricas globales, de la más reciente a la más antigua."""
    return db.scalars(
        select(MetricaEvaluacion)
        .where(
            MetricaEvaluacion.modelo_id == modelo_id,
            MetricaEvaluacion.tipo_evaluacion == tipo,
            MetricaEvaluacion.producto_id.is_(None),
        )
        .order_by(MetricaEvaluacion.periodo_hasta.desc(), MetricaEvaluacion.evaluado_en.desc())
        .limit(limite)
    ).all()


def ultimo_periodo_evaluado(db: Session, modelo_id: uuid.UUID, tipo: str) -> date | None:
    return db.scalar(
        select(func.max(MetricaEvaluacion.periodo_hasta)).where(
            MetricaEvaluacion.modelo_id == modelo_id,
            MetricaEvaluacion.tipo_evaluacion == tipo,
            MetricaEvaluacion.producto_id.is_(None),
        )
    )


def reemplazar_metricas_periodo(
    db: Session,
    modelo_id: uuid.UUID,
    tipo: str,
    desde: date,
    hasta: date,
    filas: Sequence[dict[str, Any]],
) -> None:
    """Idempotente: reevaluar un periodo sustituye las métricas previas de ese mismo periodo."""
    db.execute(
        delete(MetricaEvaluacion).where(
            MetricaEvaluacion.modelo_id == modelo_id,
            MetricaEvaluacion.tipo_evaluacion == tipo,
            MetricaEvaluacion.periodo_desde == desde,
            MetricaEvaluacion.periodo_hasta == hasta,
        )
    )
    registrar_metricas(db, filas)
