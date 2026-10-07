"""Catálogos de apoyo al frontend (`GET /catalog/routes|categories|suppliers`, abiertos a
cualquier usuario autenticado) y gestión de rutas y equipos (M02, `catalogos:*`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.catalog import CategoriaItem, ProveedorItem, RouteItem
from app.schemas.equipos import (
    EquipoReemplazo,
    EquipoRutaOut,
    RutaAdminOut,
    RutaCreate,
    RutaDesalineada,
    RutaEquipoIncompleto,
    RutaUpdate,
)
from app.services import catalog_service, equipo_service, ruta_service

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get(
    "/routes",
    response_model=list[RouteItem],
    summary="Rutas activas",
    description="Cualquier usuario autenticado. Alimenta el filtro de ruta del dashboard.",
)
def listar_rutas(db: DBSession, _usuario: CurrentUser) -> list[RouteItem]:
    return catalog_service.listar_rutas(db)


@router.get(
    "/categories",
    response_model=list[CategoriaItem],
    summary="Categorías de producto",
    description="Cualquier usuario autenticado. Alimenta el formulario de productos.",
)
def listar_categorias(db: DBSession, _usuario: CurrentUser) -> list[CategoriaItem]:
    return catalog_service.listar_categorias(db)


@router.get(
    "/suppliers",
    response_model=list[ProveedorItem],
    summary="Proveedores activos",
    description="Cualquier usuario autenticado. Alimenta el formulario de productos.",
)
def listar_proveedores(db: DBSession, _usuario: CurrentUser) -> list[ProveedorItem]:
    return catalog_service.listar_proveedores(db)


# ------------------------------------------------------------------ M02: rutas, equipos y empleados
# Las rutas estáticas (`/routes/admin`, `/teams/...`) se declaran antes que `/routes/{ruta_id}`.
PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("catalogos:leer"))]
PuedeGestionar = Annotated[UsuarioAutenticado, Depends(require_permission("catalogos:gestionar"))]


@router.get(
    "/routes/admin",
    response_model=list[RutaAdminOut],
    summary="Rutas para administración",
    description=(
        "Requiere `catalogos:leer`. Incluye inactivas (filtro `activa`) y el estado del equipo "
        "vigente (integrantes, suma de porcentajes)."
    ),
)
def listar_rutas_admin(
    db: DBSession, _usuario: PuedeLeer, activa: bool | None = None
) -> list[RutaAdminOut]:
    return ruta_service.listar(db, activa=activa)


@router.get(
    "/teams/incomplete",
    response_model=list[RutaEquipoIncompleto],
    summary="Rutas con equipo incompleto",
    description=(
        "Requiere `catalogos:leer`. Rutas activas sin equipo, sin vendedor o cuyo equipo vigente "
        "no suma 100,00."
    ),
)
def rutas_con_equipo_incompleto(db: DBSession, _usuario: PuedeLeer) -> list[RutaEquipoIncompleto]:
    return equipo_service.rutas_con_equipo_incompleto(db)


@router.get(
    "/teams/misaligned",
    response_model=list[RutaDesalineada],
    summary="Rutas con vendedor desalineado",
    description=(
        "Requiere `catalogos:leer`. Rutas cuyo `vendedor_id` difiere del usuario del empleado "
        "vendedor del equipo (dos fuentes de verdad, ADR-18)."
    ),
)
def rutas_desalineadas(db: DBSession, _usuario: PuedeLeer) -> list[RutaDesalineada]:
    return equipo_service.rutas_desalineadas(db)


@router.post(
    "/routes",
    response_model=RutaAdminOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ruta",
    description=(
        "Requiere `catalogos:gestionar`. El código se guarda en mayúsculas. 409 `RUTA_DUPLICADA`."
    ),
)
def crear_ruta(db: DBSession, actor: PuedeGestionar, datos: RutaCreate) -> RutaAdminOut:
    return ruta_service.crear(db, datos, actor.id)


@router.get(
    "/routes/{ruta_id}",
    response_model=RutaAdminOut,
    summary="Detalle de una ruta",
    description="Requiere `catalogos:leer`. 404 `RUTA_NO_ENCONTRADA`.",
)
def obtener_ruta(db: DBSession, _usuario: PuedeLeer, ruta_id: UUID) -> RutaAdminOut:
    return ruta_service.obtener(db, ruta_id)


@router.patch(
    "/routes/{ruta_id}",
    response_model=RutaAdminOut,
    summary="Actualizar ruta (parcial)",
    description=(
        "Requiere `catalogos:gestionar`. El código no se modifica. 409 `VENDEDOR_INCOHERENTE` "
        "si el usuario contradice al empleado vendedor del equipo vigente."
    ),
)
def actualizar_ruta(
    db: DBSession, actor: PuedeGestionar, ruta_id: UUID, datos: RutaUpdate
) -> RutaAdminOut:
    return ruta_service.actualizar(db, ruta_id, datos, actor.id)


@router.post(
    "/routes/{ruta_id}/deactivate",
    response_model=RutaAdminOut,
    summary="Desactivar ruta (baja lógica)",
    description=(
        "Requiere `catalogos:gestionar`. Idempotente. 409 `RUTA_CON_LIQUIDACIONES` si hay "
        "liquidaciones en borrador; 409 `RUTA_CON_CARGAS_VIGENTES` si hay cargas vigentes."
    ),
)
def desactivar_ruta(db: DBSession, actor: PuedeGestionar, ruta_id: UUID) -> RutaAdminOut:
    return ruta_service.desactivar(db, ruta_id, actor.id)


@router.post(
    "/routes/{ruta_id}/activate",
    response_model=RutaAdminOut,
    summary="Reactivar ruta",
    description="Requiere `catalogos:gestionar`. Idempotente.",
)
def activar_ruta(db: DBSession, actor: PuedeGestionar, ruta_id: UUID) -> RutaAdminOut:
    return ruta_service.activar(db, ruta_id, actor.id)


@router.get(
    "/routes/{ruta_id}/team",
    response_model=EquipoRutaOut,
    summary="Equipo de una ruta",
    description="Requiere `catalogos:leer`. Equipo vigente e historial de vigencias cerradas.",
)
def obtener_equipo(db: DBSession, _usuario: PuedeLeer, ruta_id: UUID) -> EquipoRutaOut:
    return equipo_service.obtener(db, ruta_id)


@router.put(
    "/routes/{ruta_id}/team",
    response_model=EquipoRutaOut,
    summary="Reemplazar el equipo de una ruta",
    description=(
        "Requiere `catalogos:gestionar`. Cierra las vigencias anteriores (no las borra) y crea "
        "las nuevas. 400 `EQUIPO_NO_SUMA_100`, `EMPLEADO_REPETIDO`, `VENDEDOR_MULTIPLE`, "
        "`VIGENCIA_INVALIDA`; 404 `EMPLEADO_NO_ENCONTRADO`; 409 `EMPLEADO_INACTIVO`, "
        "`VENDEDOR_INCOHERENTE`, `RUTA_INACTIVA`."
    ),
)
def reemplazar_equipo(
    db: DBSession, actor: PuedeGestionar, ruta_id: UUID, datos: EquipoReemplazo
) -> EquipoRutaOut:
    return equipo_service.reemplazar(db, ruta_id, datos, actor.id)
