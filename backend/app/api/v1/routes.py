"""Endpoint de planificación de carga de ruta (`POST /routes/load-plans`). Sin reglas de negocio:
valida el permiso según la acción y delega en `load_plan_service`."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.core.rbac import verificar_permiso
from app.schemas.routes import LoadPlanRequest, LoadPlanResponse
from app.services import load_plan_service

router = APIRouter(prefix="/routes", tags=["Routes"])

_PERMISO_POR_ACCION = {
    "generar": "carga_ruta:generar",
    "aprobar": "carga_ruta:aprobar",
    "rechazar": "carga_ruta:aprobar",
}


@router.post(
    "/load-plans",
    response_model=LoadPlanResponse,
    summary="Generación y aprobación de carga de ruta",
    description=(
        "`accion=generar` (permiso `carga_ruta:generar`) crea un plan en `borrador` con "
        "`cantidad_sugerida = min(demanda predicha, stock disponible)`; 400 "
        "`CARGA_VIGENTE_EXISTENTE` si ya hay una carga vigente para la ruta y fecha. "
        "`accion=aprobar|rechazar` (permiso `carga_ruta:aprobar`) opera sobre `carga_id`: aprobar "
        "reserva stock y registra el kardex (400 `CANTIDAD_EXCEDE_STOCK` si una cantidad excede "
        "el disponible); rechazar exige `motivo_rechazo` y libera las reservas existentes."
    ),
)
def gestionar_carga(
    db: DBSession, usuario: CurrentUser, solicitud: LoadPlanRequest
) -> LoadPlanResponse:
    verificar_permiso(usuario, _PERMISO_POR_ACCION[solicitud.accion])
    return load_plan_service.gestionar(db, solicitud, usuario.id)
