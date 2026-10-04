"""Cola de jobs asíncronos (`jobs_ml`, ADR-04)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import EstadoJob, TipoJob
from app.domain.models.ml import JobML

_ACTIVOS = (EstadoJob.EN_COLA, EstadoJob.EN_EJECUCION)


def crear(
    db: Session,
    *,
    tipo: TipoJob,
    parametros: dict[str, Any],
    solicitado_por: uuid.UUID | None = None,
    estado: EstadoJob = EstadoJob.EN_COLA,
) -> JobML:
    job = JobML(tipo=tipo, estado=estado, parametros=parametros, solicitado_por=solicitado_por)
    if estado == EstadoJob.EN_EJECUCION:
        job.iniciado_en = datetime.now(UTC)
    db.add(job)
    db.flush()
    return job


def obtener(db: Session, job_id: uuid.UUID) -> JobML | None:
    return db.get(JobML, job_id)


def activo_de_tipo(db: Session, tipo: TipoJob) -> JobML | None:
    return db.scalars(
        select(JobML).where(JobML.tipo == tipo, JobML.estado.in_(_ACTIVOS)).limit(1)
    ).first()


def en_cola_de_tipo(db: Session, tipo: TipoJob) -> JobML | None:
    """Job aún `en_cola` (sin iniciar) del tipo: permite coalescer solicitudes repetidas."""
    return db.scalars(
        select(JobML).where(JobML.tipo == tipo, JobML.estado == EstadoJob.EN_COLA).limit(1)
    ).first()


def reclamar_siguiente(db: Session, tipo: TipoJob) -> JobML | None:
    """Toma el job `en_cola` más antiguo (FOR UPDATE SKIP LOCKED) y lo pasa a `en_ejecucion`."""
    job = db.scalars(
        select(JobML)
        .where(JobML.tipo == tipo, JobML.estado == EstadoJob.EN_COLA)
        .order_by(JobML.solicitado_en)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is not None:
        job.estado = EstadoJob.EN_EJECUCION
        job.iniciado_en = datetime.now(UTC)
        db.flush()
    return job


def finalizar(
    db: Session,
    job: JobML,
    *,
    estado: EstadoJob,
    resultado_modelo_id: uuid.UUID | None = None,
    error: str | None = None,
) -> None:
    job.estado = estado
    job.finalizado_en = datetime.now(UTC)
    job.resultado_modelo_id = resultado_modelo_id
    job.error = error
    db.flush()


def ultimo_reentrenamiento_completado(db: Session) -> JobML | None:
    return db.scalars(
        select(JobML)
        .where(JobML.tipo == TipoJob.REENTRENAMIENTO, JobML.estado == EstadoJob.COMPLETADO)
        .order_by(JobML.finalizado_en.desc())
        .limit(1)
    ).first()
