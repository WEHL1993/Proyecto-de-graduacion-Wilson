"""Endpoints de abastecimiento (`/purchasing`). Sin reglas de negocio: validan el permiso y
delegan en `purchasing_service`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DBSession, require_permission
from app.core.rbac import verificar_permiso
from app.domain.enums import EstadoPedido
from app.schemas.auth import UsuarioAutenticado
from app.schemas.purchasing import (
    PedidoConfirmacion,
    PedidoCreate,
    PedidoOut,
    PedidoPage,
    SugerenciasResponse,
)
from app.services import purchasing_service

router = APIRouter(prefix="/purchasing", tags=["Purchasing"])

_LECTORES = {"pedido_proveedor:gestionar", "pedido_proveedor:confirmar", "inventario:ajustar"}

Gestiona = Annotated[UsuarioAutenticado, Depends(require_permission("pedido_proveedor:gestionar"))]
Confirma = Annotated[UsuarioAutenticado, Depends(require_permission("pedido_proveedor:confirmar"))]
Recibe = Annotated[UsuarioAutenticado, Depends(require_permission("inventario:ajustar"))]


@router.get(
    "/suggestions",
    response_model=SugerenciasResponse,
    summary="Sugerencias de reabastecimiento",
    description=(
        "Requiere `pedido_proveedor:gestionar`. `cantidad_sugerida = max(0, (demanda proyectada "
        "de los próximos N días + stock mínimo) - stock actual)`, solo para productos con "
        "proveedor. Sin modelo productivo o sin historial se sugiere por punto de reorden y se "
        "informa en `advertencias`."
    ),
)
def sugerir(
    db: DBSession,
    _usuario: Gestiona,
    horizonte_dias: Annotated[int, Query(ge=1, le=30)] = 7,
) -> SugerenciasResponse:
    return purchasing_service.sugerir(db, horizonte_dias)


@router.post(
    "/orders",
    response_model=PedidoOut,
    status_code=201,
    summary="Crear (y opcionalmente enviar) una orden de compra",
    description=(
        "Requiere `pedido_proveedor:gestionar`. Nace en `borrador`, o en `enviado` si "
        "`enviar=true`. 400 `PRODUCTO_AJENO_A_PROVEEDOR` si un producto no es del proveedor."
    ),
)
def crear_orden(db: DBSession, usuario: Gestiona, solicitud: PedidoCreate) -> PedidoOut:
    return purchasing_service.crear_pedido(db, solicitud, usuario.id)


@router.get(
    "/orders",
    response_model=PedidoPage,
    summary="Pedidos a proveedor",
    description=(
        "Requiere `pedido_proveedor:gestionar` o `inventario:ajustar` (Bodega, para recibir): "
        "todos los pedidos; o `pedido_proveedor:confirmar`: solo los del proveedor del usuario."
    ),
)
def listar_ordenes(
    db: DBSession,
    usuario: CurrentUser,
    estado: EstadoPedido | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PedidoPage:
    _verificar_lectura(usuario)
    return purchasing_service.listar(db, usuario, estado=estado, limit=limit, offset=offset)


@router.get(
    "/orders/{pedido_id}",
    response_model=PedidoOut,
    summary="Detalle de un pedido",
    description="Mismos permisos y aislamiento que el listado; 404 si es de otro proveedor.",
)
def obtener_orden(db: DBSession, usuario: CurrentUser, pedido_id: UUID) -> PedidoOut:
    _verificar_lectura(usuario)
    return purchasing_service.obtener(db, usuario, pedido_id)


@router.post(
    "/orders/{pedido_id}/send",
    response_model=PedidoOut,
    summary="Aprobar y enviar la orden al proveedor (borrador → enviado)",
    description="Requiere `pedido_proveedor:gestionar`.",
)
def enviar_orden(db: DBSession, _usuario: Gestiona, pedido_id: UUID) -> PedidoOut:
    return purchasing_service.enviar(db, pedido_id)


@router.post(
    "/orders/{pedido_id}/cancel",
    response_model=PedidoOut,
    summary="Cancelar una orden (borrador|enviado → cancelado)",
    description="Requiere `pedido_proveedor:gestionar`.",
)
def cancelar_orden(db: DBSession, _usuario: Gestiona, pedido_id: UUID) -> PedidoOut:
    return purchasing_service.cancelar(db, pedido_id)


@router.patch(
    "/orders/{pedido_id}/confirm",
    response_model=PedidoOut,
    summary="Confirmación del proveedor (enviado → confirmado)",
    description=(
        "Requiere `pedido_proveedor:confirmar`. Aislamiento por `proveedor_id`: un pedido de "
        "otro proveedor responde 404 `PEDIDO_NO_ENCONTRADO`."
    ),
)
def confirmar_orden(
    db: DBSession, usuario: Confirma, pedido_id: UUID, solicitud: PedidoConfirmacion
) -> PedidoOut:
    return purchasing_service.confirmar(db, usuario, pedido_id, solicitud)


@router.post(
    "/orders/{pedido_id}/receive",
    response_model=PedidoOut,
    summary="Recepción física en bodega (confirmado → recibido)",
    description=(
        "Requiere `inventario:ajustar` (Bodega). Registra la entrada en el kardex e incrementa "
        "`stock_actual` en `inventario`."
    ),
)
def recibir_orden(db: DBSession, usuario: Recibe, pedido_id: UUID) -> PedidoOut:
    return purchasing_service.recibir(db, pedido_id, usuario.id)


def _verificar_lectura(usuario: UsuarioAutenticado) -> None:
    if not _LECTORES & set(usuario.permisos):
        verificar_permiso(usuario, "pedido_proveedor:gestionar")
