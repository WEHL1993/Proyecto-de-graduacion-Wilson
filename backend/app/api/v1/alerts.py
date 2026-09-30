"""Bandeja de alertas (`GET /alerts`). Sin reglas de negocio: delega en `alert_service`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSession, require_permission
from app.domain.enums import EstadoAlerta
from app.schemas.alerts import AlertItem, AlertList
from app.schemas.auth import UsuarioAutenticado
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])

PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("alertas:leer"))]


@router.get(
    "",
    response_model=AlertList,
    summary="Bandeja de alertas",
    description=(
        "Requiere permiso `alertas:leer`. Solo devuelve los tipos que corresponden al rol del "
        "usuario (stock/quiebre → inventario y compras; `mape_umbral` → Gerente/Admin; "
        "`etl_error` → quienes cargan datos). Críticas primero, luego las más recientes."
    ),
)
def listar_alertas(
    db: DBSession,
    usuario: PuedeLeer,
    estado: EstadoAlerta | None = EstadoAlerta.ABIERTA,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AlertList:
    return alert_service.listar(db, usuario, estado=estado, limite=limit)


@router.patch(
    "/{alerta_id}/acknowledge",
    response_model=AlertItem,
    summary="Reconocer una alerta abierta",
    description=(
        "Requiere `alertas:leer`. Pasa la alerta a `reconocida`. 404 `ALERTA_NO_ENCONTRADA` "
        "(inexistente o de un tipo no visible para el rol); 409 `ALERTA_NO_ABIERTA`."
    ),
)
def reconocer_alerta(db: DBSession, usuario: PuedeLeer, alerta_id: UUID) -> AlertItem:
    return alert_service.reconocer(db, usuario, alerta_id)
