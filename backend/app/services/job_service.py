"""Ciclo de vida de los jobs asíncronos (`jobs_ml`) que consume el Worker (ADR-04)."""

import logging
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoJob, TipoJob
from app.repositories import job_repo
from app.schemas.ml import JobStatus
from app.services import monitoring_service, retraining_service
from app.services.bitacora_service import auditar

logger = logging.getLogger(__name__)


@auditar
def obtener_estado(db: Session, job_id: uuid.UUID) -> JobStatus:
    job = job_repo.obtener(db, job_id)
    if job is None:
        raise AppError("JOB_NO_ENCONTRADO", "El job indicado no existe.", status_code=404)
    return JobStatus(
        job_id=job.id,
        tipo=job.tipo,
        estado=job.estado,
        parametros=job.parametros,
        resultado_modelo_id=job.resultado_modelo_id,
        solicitado_en=job.solicitado_en,
        iniciado_en=job.iniciado_en,
        finalizado_en=job.finalizado_en,
        error=job.error,
    )


@auditar
def procesar_siguiente_reentrenamiento(db: Session) -> uuid.UUID | None:
    """Reclama y ejecuta el reentrenamiento más antiguo en cola; `None` si no hay ninguno."""
    job = job_repo.reclamar_siguiente(db, TipoJob.REENTRENAMIENTO)
    if job is None:
        return None
    db.commit()  # publica `en_ejecucion` antes del entrenamiento (visible en GET /ml/jobs)
    try:
        retraining_service.ejecutar(db, job)
    except Exception as exc:
        db.rollback()
        logger.exception("Reentrenamiento %s falló", job.id)
        job_repo.finalizar(db, job, estado=EstadoJob.FALLIDO, error=str(exc))
        db.commit()
    return job.id


@auditar
def procesar_evaluacion_en_cola(db: Session) -> uuid.UUID | None:
    """Reclama y ejecuta la evaluación en cola (p. ej. encolada al cerrar una liquidación, ADR-14).

    Evalúa los periodos pendientes del modelo productivo; no entrena. `None` si no hay ninguna.
    """
    job = job_repo.reclamar_siguiente(db, TipoJob.EVALUACION_PRODUCCION)
    if job is None:
        return None
    db.commit()  # publica `en_ejecucion` antes de evaluar
    try:
        monitoring_service.evaluar_produccion(db)
    except Exception as exc:
        db.rollback()
        logger.exception("Evaluación en cola %s falló", job.id)
        job_repo.finalizar(db, job, estado=EstadoJob.FALLIDO, error=str(exc))
        db.commit()
        return job.id
    job_repo.finalizar(db, job, estado=EstadoJob.COMPLETADO)
    db.commit()
    return job.id


@auditar
def ejecutar_evaluacion(
    db: Session, *, desde: date | None = None, hasta: date | None = None
) -> monitoring_service.ResultadoEvaluacion:
    """Evalúa el modelo productivo dejando traza del job en `jobs_ml`."""
    job = job_repo.crear(
        db,
        tipo=TipoJob.EVALUACION_PRODUCCION,
        estado=EstadoJob.EN_EJECUCION,
        parametros={
            "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None,
        },
    )
    db.commit()
    try:
        resultado = monitoring_service.evaluar_produccion(db, desde=desde, hasta=hasta)
    except Exception as exc:
        db.rollback()
        job_repo.finalizar(db, job, estado=EstadoJob.FALLIDO, error=str(exc))
        db.commit()
        raise
    job_repo.finalizar(db, job, estado=EstadoJob.COMPLETADO)
    db.commit()
    return resultado
