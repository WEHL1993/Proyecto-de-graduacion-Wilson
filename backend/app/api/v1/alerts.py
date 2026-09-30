"""Bandeja de alertas (`GET /alerts`). Sin reglas de negocio: delega en `alert_service`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSession, require_permission
from app.domain.enums import EstadoAlerta
from app.schemas.alerts import AlertList
from app.schemas.auth import UsuarioAutenticado
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])

PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("alertas:leer"))]


@router.get(
    "",
    response_model=AlertList,
    summary="Bandeja de alertas",
    description="Requiere permiso `alertas:leer`. Críticas primero, luego las más recientes.",
)
def listar_alertas(
    db: DBSession,
    _usuario: PuedeLeer,
    estado: EstadoAlerta | None = EstadoAlerta.ABIERTA,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AlertList:
    return alert_service.listar(db, estado=estado, limite=limit)
