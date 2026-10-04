"""Endpoints de existencias, kardex y ajuste manual. Sin reglas de negocio: delegan en
`inventory_service`."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DBSession, require_permission
from app.domain.enums import TipoMovimiento
from app.schemas.auth import UsuarioAutenticado
from app.schemas.inventory import AjusteRequest, AjusteResponse, KardexPage, StockPage
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory"])

PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("inventario:leer"))]
PuedeAjustar = Annotated[UsuarioAutenticado, Depends(require_permission("inventario:ajustar"))]
Limite = Annotated[int, Query(ge=1, le=200)]
Desplazamiento = Annotated[int, Query(ge=0)]


@router.get(
    "",
    response_model=StockPage,
    summary="Existencias por producto",
    description=(
        "Requiere permiso `inventario:leer`. `stock_disponible = stock_actual - stock_reservado`. "
        "Un producto sin fila de inventario se reporta con existencias en 0."
    ),
)
def listar_existencias(
    db: DBSession,
    _usuario: PuedeLeer,
    producto_id: UUID | None = None,
    bajo_minimo: bool = False,
    limit: Limite = 50,
    offset: Desplazamiento = 0,
) -> StockPage:
    return inventory_service.listar_existencias(
        db, producto_id=producto_id, solo_bajo_minimo=bajo_minimo, limit=limit, offset=offset
    )


@router.get(
    "/kardex",
    response_model=KardexPage,
    summary="Movimientos de kardex",
    description="Requiere permiso `inventario:leer`. Orden: más reciente primero.",
)
def listar_kardex(
    db: DBSession,
    _usuario: PuedeLeer,
    producto_id: UUID | None = None,
    tipo_movimiento: TipoMovimiento | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: Limite = 50,
    offset: Desplazamiento = 0,
) -> KardexPage:
    return inventory_service.listar_kardex(
        db,
        producto_id=producto_id,
        tipo=tipo_movimiento,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/adjustments",
    response_model=AjusteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ajuste manual de existencias",
    description=(
        "Requiere `inventario:ajustar`. Tipos: `incremento`, `decremento`, `fijar`. Registra un "
        "movimiento `ajuste` en el kardex (cantidad con signo) con el motivo. 404 "
        "`PRODUCTO_NO_ENCONTRADO`; 409 `PRODUCTO_INACTIVO`; 400 `STOCK_INSUFICIENTE` si deja el "
        "stock bajo lo reservado, `CANTIDAD_INVALIDA` o `AJUSTE_SIN_CAMBIO`."
    ),
)
def ajustar_existencias(
    db: DBSession, actor: PuedeAjustar, solicitud: AjusteRequest
) -> AjusteResponse:
    return inventory_service.ajustar_existencias(db, solicitud, actor.id)
