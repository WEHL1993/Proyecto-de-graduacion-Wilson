"""Consulta de la bitácora de auditoría (`/bitacora`). Solo lectura: el registro lo generan el
middleware, `@auditar` y el Worker; nadie puede modificarlo ni borrarlo desde la API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.bitacora import BitacoraPage
from app.services import bitacora_service

router = APIRouter(prefix="/bitacora", tags=["Bitácora"])

Auditor = Annotated[UsuarioAutenticado, Depends(require_permission("bitacora:leer"))]


@router.get(
    "",
    response_model=BitacoraPage,
    summary="Consultar la bitácora de auditoría",
    description=(
        "Requiere `bitacora:leer` (Admin). Más reciente primero. Filtros: rango de fechas, "
        "usuario, acción (texto parcial), origen (`http|servicio|worker`), resultado "
        "(`exito|error`) y `request_id` (une la petición HTTP con sus casos de uso)."
    ),
)
def consultar_bitacora(
    db: DBSession,
    _usuario: Auditor,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    usuario_id: UUID | None = None,
    accion: str | None = None,
    origen: Annotated[str | None, Query(pattern="^(http|servicio|worker)$")] = None,
    resultado: Annotated[str | None, Query(pattern="^(exito|error)$")] = None,
    request_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BitacoraPage:
    return bitacora_service.listar(
        db,
        desde=desde,
        hasta=hasta,
        usuario_id=usuario_id,
        accion=accion,
        origen=origen,
        resultado=resultado,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
