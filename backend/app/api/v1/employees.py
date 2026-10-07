"""Personal de ruta (`/employees`, M02). Lectura con `catalogos:leer`; escritura con
`catalogos:gestionar`. Baja lógica, nunca borrado físico."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.equipos import EmpleadoCreate, EmpleadoOut, EmpleadoPage, EmpleadoUpdate
from app.services import empleado_service

router = APIRouter(prefix="/employees", tags=["Employees"])

PuedeLeer = Annotated[UsuarioAutenticado, Depends(require_permission("catalogos:leer"))]
PuedeGestionar = Annotated[UsuarioAutenticado, Depends(require_permission("catalogos:gestionar"))]


@router.get(
    "",
    response_model=EmpleadoPage,
    summary="Listar empleados",
    description="Requiere `catalogos:leer`. Por defecto solo activos; filtro `q` por nombre.",
)
def listar_empleados(
    db: DBSession,
    _usuario: PuedeLeer,
    activo: bool | None = True,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EmpleadoPage:
    return empleado_service.listar(db, activo=activo, q=q, limit=limit, offset=offset)


@router.get(
    "/{empleado_id}",
    response_model=EmpleadoOut,
    summary="Detalle de un empleado",
    description="Requiere `catalogos:leer`. 404 `EMPLEADO_NO_ENCONTRADO`.",
)
def obtener_empleado(db: DBSession, _usuario: PuedeLeer, empleado_id: UUID) -> EmpleadoOut:
    return empleado_service.obtener(db, empleado_id)


@router.post(
    "",
    response_model=EmpleadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear empleado",
    description=(
        "Requiere `catalogos:gestionar`. `usuario_id` es opcional y único. 404 "
        "`USUARIO_NO_ENCONTRADO`; 409 `USUARIO_YA_VINCULADO`."
    ),
)
def crear_empleado(db: DBSession, actor: PuedeGestionar, datos: EmpleadoCreate) -> EmpleadoOut:
    return empleado_service.crear(db, datos, actor.id)


@router.patch(
    "/{empleado_id}",
    response_model=EmpleadoOut,
    summary="Actualizar empleado (parcial)",
    description="Requiere `catalogos:gestionar`. `usuario_id: null` desvincula al usuario.",
)
def actualizar_empleado(
    db: DBSession, actor: PuedeGestionar, empleado_id: UUID, datos: EmpleadoUpdate
) -> EmpleadoOut:
    return empleado_service.actualizar(db, empleado_id, datos, actor.id)


@router.delete(
    "/{empleado_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja un empleado (baja lógica)",
    description=(
        "Requiere `catalogos:gestionar`. Idempotente. 409 `EMPLEADO_EN_USO` si integra el "
        "equipo vigente de una ruta."
    ),
)
def eliminar_empleado(db: DBSession, actor: PuedeGestionar, empleado_id: UUID) -> Response:
    empleado_service.dar_de_baja(db, empleado_id, actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{empleado_id}/reactivate",
    response_model=EmpleadoOut,
    summary="Reactivar un empleado",
    description="Requiere `catalogos:gestionar`. Idempotente.",
)
def reactivar_empleado(db: DBSession, actor: PuedeGestionar, empleado_id: UUID) -> EmpleadoOut:
    return empleado_service.reactivar(db, empleado_id, actor.id)
