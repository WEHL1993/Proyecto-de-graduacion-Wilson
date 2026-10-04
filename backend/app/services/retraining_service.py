"""Caso de uso: reentrenamiento asíncrono con promoción condicionada (ADR-03, ADR-04, ADR-12).

`solicitar` solo encola un job en `jobs_ml` (POST /ml/models/retrain). El Worker ejecuta
`ejecutar`: entrena un candidato por algoritmo, elige el de menor MAPE y lo promueve **solo si
mejora estrictamente** al modelo productivo (TC-ML-02/03). El MAPE de referencia del productivo
es el observado en producción (último periodo evaluado); si aún no hay, su MAPE de holdout.
El MAPE del candidato es el de su holdout global.
"""

import logging
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import (
    EstadoJob,
    MotivoEntrenamiento,
    Severidad,
    TipoAlerta,
    TipoEvaluacion,
    TipoJob,
)
from app.domain.models.ml import JobML, ModeloML
from app.ml import contracts
from app.repositories import alert_repo, job_repo, model_repo, parametro_repo
from app.schemas.ml import RetrainRequest, RetrainResponse
from app.services import training_service
from app.services.bitacora_service import auditar

logger = logging.getLogger(__name__)


@auditar
def solicitar(db: Session, solicitud: RetrainRequest, usuario_id: uuid.UUID) -> RetrainResponse:
    activo = job_repo.activo_de_tipo(db, TipoJob.REENTRENAMIENTO)
    if activo is not None:
        raise AppError(
            "REENTRENAMIENTO_EN_CURSO",
            "Ya hay un reentrenamiento en cola o en ejecución.",
            detalle={"job_id": str(activo.id), "estado": activo.estado},
        )
    job = job_repo.crear(
        db,
        tipo=TipoJob.REENTRENAMIENTO,
        solicitado_por=usuario_id,
        parametros={
            "algoritmos": [a.value for a in solicitud.algoritmos],
            "motivo": solicitud.motivo.value,
            "ventana_desde": _iso(solicitud.ventana_desde),
            "ventana_hasta": _iso(solicitud.ventana_hasta),
            "promover_automaticamente": solicitud.promover_automaticamente,
        },
    )
    db.commit()
    return RetrainResponse(job_id=job.id, estado="en_cola", solicitado_en=job.solicitado_en)


@auditar
def ejecutar(db: Session, job: JobML) -> JobML:
    """Ejecuta un job de reentrenamiento ya reclamado (`en_ejecucion`) y lo cierra."""
    parametros = job.parametros
    algoritmos: list[str] = parametros.get("algoritmos") or []
    motivo = MotivoEntrenamiento(parametros.get("motivo", MotivoEntrenamiento.MANUAL))
    desde = _fecha(parametros.get("ventana_desde"))
    hasta = _fecha(parametros.get("ventana_hasta"))
    promover = bool(parametros.get("promover_automaticamente", True))
    productivo = model_repo.obtener_produccion(db, get_settings().ml_modelo_nombre)
    fuente = parametro_repo.fuente_reentrenamiento(db)  # ADR-14: base Excel + liquidaciones

    candidatos: list[ModeloML] = []
    errores: list[str] = []
    for algoritmo in algoritmos:
        try:
            candidatos.append(
                training_service.entrenar_modelo(
                    db,
                    algoritmo=algoritmo,
                    motivo=motivo,
                    entrenado_por=job.solicitado_por,
                    ventana_desde=desde,
                    ventana_hasta=hasta,
                    fuente=fuente,
                )
            )
        except AppError as exc:
            db.rollback()
            errores.append(f"{algoritmo}: {exc.mensaje}")
        except Exception as exc:  # el job debe cerrarse como `fallido`, no tumbar al Worker
            db.rollback()
            logger.exception("Fallo inesperado entrenando %s", algoritmo)
            errores.append(f"{algoritmo}: {exc}")

    if not candidatos:
        job_repo.finalizar(
            db,
            job,
            estado=EstadoJob.FALLIDO,
            error="; ".join(errores) or "No se solicitó ningún algoritmo.",
        )
        db.commit()
        return job

    mejor = min(candidatos, key=lambda c: _clave_orden(_mape_candidato(db, c)))
    if promover:
        _decidir_promocion(db, mejor, candidatos, productivo)
    job_repo.finalizar(
        db,
        job,
        estado=EstadoJob.COMPLETADO,
        resultado_modelo_id=mejor.id,
        error="; ".join(errores) or None,
    )
    db.commit()
    return job


def _decidir_promocion(
    db: Session, mejor: ModeloML, candidatos: list[ModeloML], productivo: ModeloML | None
) -> None:
    mape_mejor = _mape_candidato(db, mejor)
    referencia = None if productivo is None else _mape_referencia(db, productivo)
    mejora = productivo is None or (
        mape_mejor is not None and (referencia is None or mape_mejor < referencia)
    )
    if mejora:
        contracts.promover_a_produccion(db, mejor.id)
        if productivo is not None:
            alert_repo.resolver_abiertas_de_modelo(
                db, tipo=TipoAlerta.MAPE_UMBRAL, modelo_id=productivo.id
            )
        descartados = [c for c in candidatos if c.id != mejor.id]
    else:
        alert_repo.crear(
            db,
            tipo=TipoAlerta.MAPE_UMBRAL,
            severidad=Severidad.INFO,
            modelo_id=mejor.id,
            mensaje=(
                f"Reentrenamiento finalizado: el mejor candidato ({mejor.algoritmo} "
                f"{mejor.version}, MAPE {_fmt(mape_mejor)}) no mejora al modelo productivo "
                f"(MAPE {_fmt(referencia)}). Se mantiene el modelo productivo."
            ),
        )
        descartados = candidatos
    for candidato in descartados:
        model_repo.descartar(db, candidato)


def _mape_candidato(db: Session, modelo: ModeloML) -> float | None:
    return _ultimo_mape(db, modelo, TipoEvaluacion.HOLDOUT)


def _mape_referencia(db: Session, productivo: ModeloML) -> float | None:
    observado = _ultimo_mape(db, productivo, TipoEvaluacion.PRODUCCION)
    if observado is not None:
        return observado
    return _ultimo_mape(db, productivo, TipoEvaluacion.HOLDOUT)


def _ultimo_mape(db: Session, modelo: ModeloML, tipo: TipoEvaluacion) -> float | None:
    filas = model_repo.ultimas_globales(db, modelo.id, tipo.value, limite=1)
    if not filas or filas[0].mape is None:
        return None
    return float(filas[0].mape)


def _clave_orden(mape: float | None) -> tuple[bool, float]:
    return (mape is None, mape if mape is not None else 0.0)


def _fmt(mape: float | None) -> str:
    return "s/d" if mape is None else f"{mape:.1f} %"


def _iso(valor: date | None) -> str | None:
    return None if valor is None else valor.isoformat()


def _fecha(valor: object) -> date | None:
    return date.fromisoformat(valor) if isinstance(valor, str) and valor else None
