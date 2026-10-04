"""Liquidación diaria de ventas (ADR-14). Sin reglas de negocio: valida permisos y delega en
`liquidacion_service`."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSession, require_permission
from app.domain.enums import EstadoLiquidacion
from app.schemas.auth import UsuarioAutenticado
from app.schemas.liquidacion import (
    AnulacionRequest,
    CorreccionRequest,
    LiquidacionConfig,
    LiquidacionRequest,
    LiquidacionResponse,
    ListadoLiquidaciones,
    PrecargaResponse,
)
from app.services import liquidacion_service

router = APIRouter(prefix="/liquidaciones", tags=["Liquidaciones"])

PuedeRegistrar = Annotated[
    UsuarioAutenticado, Depends(require_permission("liquidaciones:registrar"))
]
PuedeCerrar = Annotated[UsuarioAutenticado, Depends(require_permission("liquidaciones:cerrar"))]
PuedeCorregir = Annotated[UsuarioAutenticado, Depends(require_permission("liquidaciones:corregir"))]
PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("liquidaciones:leer"))]

_ERRORES_ESTADO = {
    404: {"description": "`LIQUIDACION_NO_ENCONTRADA`"},
    409: {"description": "Conflicto de estado de la liquidación"},
}


@router.post(
    "",
    response_model=LiquidacionResponse,
    summary="Crear o actualizar el borrador de la liquidación del día",
    description=(
        "Requiere `liquidaciones:registrar`. Un borrador puede guardarse incompleto y **no** "
        "afecta al modelo. 400: `VENTA_FECHA_FUTURA`, `PRODUCTO_DUPLICADO_EN_CIERRE`, "
        "`PRODUCTO_INACTIVO`, `UNIDADES_NO_CUADRAN` (vendido + devuelto + merma excede lo "
        "cargado), "
        "`CARGA_REQUIERE_JUSTIFICACION`. 409 `LIQUIDACION_DUPLICADA` si ya está cerrada."
    ),
)
def guardar_borrador(
    db: DBSession, usuario: PuedeRegistrar, solicitud: LiquidacionRequest
) -> LiquidacionResponse:
    return liquidacion_service.guardar_borrador(db, solicitud, usuario.id)


@router.get(
    "/precarga",
    response_model=PrecargaResponse,
    summary="Precarga de la pantalla: carga despachada y liquidación vigente",
    description=(
        "Requiere `liquidaciones:registrar`. Devuelve las presentaciones con la cantidad "
        "despachada a la ruta ese día (editable, con justificación) y la liquidación vigente de "
        "la fecha/ruta si existe. Sin carga despachada devuelve una advertencia, no un error."
    ),
)
def precargar(
    db: DBSession,
    _usuario: PuedeRegistrar,
    fecha: date,
    ruta_id: UUID,
    vendedor_id: UUID | None = None,
) -> PrecargaResponse:
    return liquidacion_service.precargar(db, fecha, ruta_id, vendedor_id)


@router.get(
    "/config",
    response_model=LiquidacionConfig,
    summary="Umbral de diferencia de caja",
    description="Requiere `liquidaciones:leer`.",
)
def obtener_config(db: DBSession, _usuario: PuedeLeer) -> LiquidacionConfig:
    return liquidacion_service.obtener_config(db)


@router.put(
    "/config",
    response_model=LiquidacionConfig,
    summary="Actualiza el umbral de diferencia de caja",
    description="Requiere `liquidaciones:corregir` (Administrador). Auditado.",
)
def actualizar_config(
    db: DBSession, usuario: PuedeCorregir, config: LiquidacionConfig
) -> LiquidacionConfig:
    return liquidacion_service.actualizar_config(db, config, usuario.id)


@router.get(
    "",
    response_model=ListadoLiquidaciones,
    summary="Historial de liquidaciones",
    description=(
        "Requiere `liquidaciones:leer` (Administrador y Gerente). Filtros por rango de fechas, "
        "ruta, vendedor y estado; paginado, más recientes primero."
    ),
)
def listar(
    db: DBSession,
    _usuario: PuedeLeer,
    desde: date | None = None,
    hasta: date | None = None,
    ruta_id: UUID | None = None,
    vendedor_id: UUID | None = None,
    estado: EstadoLiquidacion | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListadoLiquidaciones:
    return liquidacion_service.listar(
        db,
        desde=desde,
        hasta=hasta,
        ruta_id=ruta_id,
        vendedor_id=vendedor_id,
        estado=estado,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{liquidacion_id}",
    response_model=LiquidacionResponse,
    summary="Detalle de una liquidación",
    description="Requiere `liquidaciones:leer`. 404 `LIQUIDACION_NO_ENCONTRADA`.",
    responses={404: _ERRORES_ESTADO[404]},
)
def obtener(db: DBSession, _usuario: PuedeLeer, liquidacion_id: UUID) -> LiquidacionResponse:
    return liquidacion_service.obtener(db, liquidacion_id)


@router.post(
    "/{liquidacion_id}/cerrar",
    response_model=LiquidacionResponse,
    summary="Cerrar la liquidación (alimenta el modelo)",
    description=(
        "Requiere `liquidaciones:cerrar`. Valida el cuadre de unidades "
        "(400 `UNIDADES_NO_CUADRAN`) y de dinero (400 `MONTOS_NO_CUADRAN`); la diferencia de "
        "caja no bloquea: se registra y, sobre el umbral, genera una alerta. En una sola "
        "transacción escribe `ventas_historicas` (origen `liquidacion`), rellena `demanda_real`, "
        "encola `evaluate_production` y audita. 409 `LIQUIDACION_YA_CERRADA`, "
        "`LIQUIDACION_YA_ANULADA`, `VENTAS_EXCEL_EXISTENTES`."
    ),
    responses=_ERRORES_ESTADO,
)
def cerrar(db: DBSession, usuario: PuedeCerrar, liquidacion_id: UUID) -> LiquidacionResponse:
    return liquidacion_service.cerrar(db, liquidacion_id, usuario.id)


@router.post(
    "/{liquidacion_id}/corregir",
    response_model=LiquidacionResponse,
    summary="Corregir una liquidación cerrada",
    description=(
        "Requiere `liquidaciones:corregir`. Incrementa `version`, hace UPSERT en "
        "`ventas_historicas`, recalcula `demanda_real` y vuelve a encolar la evaluación; deja "
        "auditoría con el motivo. 409 `LIQUIDACION_NO_CERRADA`."
    ),
    responses=_ERRORES_ESTADO,
)
def corregir(
    db: DBSession, usuario: PuedeCorregir, liquidacion_id: UUID, solicitud: CorreccionRequest
) -> LiquidacionResponse:
    return liquidacion_service.corregir(db, liquidacion_id, solicitud, usuario.id)


@router.post(
    "/{liquidacion_id}/anular",
    response_model=LiquidacionResponse,
    summary="Anular una liquidación",
    description=(
        "Requiere `liquidaciones:corregir`. Motivo obligatorio. Si estaba cerrada revierte su "
        "efecto en `ventas_historicas` y `demanda_real`. 409 `LIQUIDACION_YA_ANULADA`."
    ),
    responses=_ERRORES_ESTADO,
)
def anular(
    db: DBSession, usuario: PuedeCorregir, liquidacion_id: UUID, solicitud: AnulacionRequest
) -> LiquidacionResponse:
    return liquidacion_service.anular(db, liquidacion_id, solicitud.motivo, usuario.id)
