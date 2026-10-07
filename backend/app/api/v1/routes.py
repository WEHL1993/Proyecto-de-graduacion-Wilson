"""Endpoint de planificación de carga de ruta (`POST /routes/load-plans`). Sin reglas de negocio:
valida el permiso según la acción y delega en `load_plan_service`."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.core.rbac import verificar_permiso
from app.schemas.routes import LoadPlanRequest, LoadPlanResponse
from app.services import load_plan_service

router = APIRouter(prefix="/routes", tags=["Routes"])

_PERMISO_POR_ACCION = {
    "generar": "carga_ruta:generar",
    "enviar": "carga_ruta:generar",
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
        "`accion=enviar` (permiso `carga_ruta:generar`) pasa un `borrador` a "
        "`pendiente_aprobacion`. "
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


@router.get(
    "/load-plans",
    response_model=LoadPlanResponse,
    summary="Carga vigente de una ruta y fecha",
    description=(
        "Requiere `carga_ruta:generar` o `carga_ruta:aprobar`. Devuelve la carga vigente "
        "(borrador, pendiente o aprobada) o 404 `CARGA_NO_ENCONTRADA`."
    ),
)
def obtener_carga_vigente(
    db: DBSession, usuario: CurrentUser, ruta_id: UUID, fecha_operacion: date
) -> LoadPlanResponse:
    if not {"carga_ruta:generar", "carga_ruta:aprobar"} & set(usuario.permisos):
        verificar_permiso(usuario, "carga_ruta:generar")
    return load_plan_service.obtener_vigente(db, ruta_id, fecha_operacion)


@router.post(
    "/load-plans/{carga_id}/dispatch",
    response_model=LoadPlanResponse,
    summary="Despacho físico de una carga aprobada",
    description=(
        "Requiere `carga_ruta:despachar` (EncargadoBodega). Solo una carga `aprobada` puede "
        "despacharse (400 `ESTADO_CARGA_INVALIDO`); descuenta `stock_reservado` y `stock_actual` "
        "con la cantidad aprobada y registra la salida en el kardex (400 `STOCK_INSUFICIENTE` "
        "si la existencia física no alcanza)."
    ),
)
def despachar_carga(db: DBSession, usuario: CurrentUser, carga_id: UUID) -> LoadPlanResponse:
    verificar_permiso(usuario, "carga_ruta:despachar")
    return load_plan_service.despachar(db, carga_id, usuario.id)
