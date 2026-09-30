"""Gobernanza ML: métricas/degradación y reentrenamiento. Sin reglas de negocio: valida
permisos y delega en `monitoring_service`, `retraining_service` y `job_service`."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSession, require_permission
from app.domain.enums import TipoEvaluacion
from app.schemas.auth import UsuarioAutenticado
from app.schemas.ml import (
    JobStatus,
    MetricsResponse,
    MlConfig,
    ModelList,
    RetrainRequest,
    RetrainResponse,
)
from app.services import job_service, monitoring_service, retraining_service

router = APIRouter(prefix="/ml", tags=["ML"])

PuedeLeerMetricas = Annotated[UsuarioAutenticado, Depends(require_permission("ml:metricas:leer"))]
PuedeReentrenar = Annotated[UsuarioAutenticado, Depends(require_permission("ml:reentrenar"))]


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Consulta de precisión y degradación",
    description=(
        "Requiere permiso `ml:metricas:leer`. Si se omite `modelo_id` se usa el modelo en "
        "producción (400 `SIN_MODELO_PRODUCTIVO` si no hay). `resumen` = periodo más reciente "
        "de `serie`; `peores_productos` = top por MAPE del último periodo en el rango. "
        "422 si `desde` > `hasta`."
    ),
)
def consultar_metricas(
    db: DBSession,
    _usuario: PuedeLeerMetricas,
    desde: date,
    hasta: date,
    modelo_id: UUID | None = None,
    tipo_evaluacion: TipoEvaluacion = TipoEvaluacion.PRODUCCION,
    producto_id: UUID | None = None,
) -> MetricsResponse:
    return monitoring_service.consultar_metricas(
        db,
        modelo_id=modelo_id,
        tipo=tipo_evaluacion,
        desde=desde,
        hasta=hasta,
        producto_id=producto_id,
    )


@router.post(
    "/models/retrain",
    response_model=RetrainResponse,
    summary="Disparo de reentrenamiento",
    description=(
        "Requiere permiso `ml:reentrenar` (403 `PERMISO_DENEGADO` en caso contrario, sin crear "
        "job). Encola un job asíncrono y responde con `job_id` y estado `en_cola`; el candidato "
        "solo se promueve si mejora al modelo en producción. 400 `REENTRENAMIENTO_EN_CURSO` si "
        "ya hay uno activo."
    ),
)
def reentrenar(
    db: DBSession, usuario: PuedeReentrenar, solicitud: RetrainRequest
) -> RetrainResponse:
    return retraining_service.solicitar(db, solicitud, usuario.id)


@router.get(
    "/models",
    response_model=ModelList,
    summary="Historial de modelos",
    description="Requiere permiso `ml:metricas:leer`. Más reciente primero (máx. 20).",
)
def listar_modelos(db: DBSession, _usuario: PuedeLeerMetricas) -> ModelList:
    return ModelList(modelos=monitoring_service.listar_modelos(db))


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    summary="Estado de un job asíncrono",
    description="Requiere permiso `ml:metricas:leer`. Muestra el progreso del reentrenamiento.",
)
def estado_job(db: DBSession, _usuario: PuedeLeerMetricas, job_id: UUID) -> JobStatus:
    return job_service.obtener_estado(db, job_id)


@router.get(
    "/config",
    response_model=MlConfig,
    summary="Umbral de degradación vigente",
    description="Requiere permiso `ml:metricas:leer`. Lee `ml.mape_umbral` y periodos.",
)
def obtener_config(db: DBSession, _usuario: PuedeLeerMetricas) -> MlConfig:
    return monitoring_service.obtener_config(db)


@router.put(
    "/config",
    response_model=MlConfig,
    summary="Guardar umbral de degradación",
    description="Requiere permiso `ml:reentrenar`. Actualiza `parametros_sistema` (ADR-08).",
)
def guardar_config(db: DBSession, usuario: PuedeReentrenar, config: MlConfig) -> MlConfig:
    return monitoring_service.actualizar_config(db, config, usuario.id)
