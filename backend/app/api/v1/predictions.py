"""Endpoint de inferencia (`POST /predictions/demand`). Sin reglas de negocio: delega en
`prediction_service`."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.predictions import DemandRequest, DemandResponse
from app.services import prediction_service

router = APIRouter(prefix="/predictions", tags=["Predictions"])

PuedeConsultar = Annotated[UsuarioAutenticado, Depends(require_permission("prediccion:consultar"))]


@router.post(
    "/demand",
    response_model=DemandResponse,
    response_model_exclude_none=True,
    summary="Inferencia de demanda por producto/ruta/horizonte",
    description=(
        "Requiere permiso `prediccion:consultar`. Usa el modelo en estado `produccion` "
        "(400 `SIN_MODELO_PRODUCTIVO` si no existe). El intervalo es al 95 %. Con "
        "`persistir=true` guarda los puntos en `pronosticos_demanda` (idempotente). 400 "
        "`HISTORIAL_INSUFICIENTE` si el producto/ruta no tiene historial previo a `fecha_base`; "
        "500 `ARTEFACTO_CORRUPTO` si el hash del artefacto no coincide (no se sirve predicción)."
    ),
    responses={
        400: {"description": "`SIN_MODELO_PRODUCTIVO` o `HISTORIAL_INSUFICIENTE`"},
        500: {"description": "`ARTEFACTO_CORRUPTO`: hash del artefacto inválido; alerta crítica"},
    },
)
def predecir_demanda(
    db: DBSession, _usuario: PuedeConsultar, solicitud: DemandRequest
) -> DemandResponse:
    return prediction_service.predecir_demanda(db, solicitud)
