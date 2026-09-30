"""Gestión administrativa de usuarios (`/users`). Sin reglas de negocio: delega en
`user_service`. Todo el módulo exige `usuarios:gestionar`."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.users import (
    RolItem,
    UsuarioCreate,
    UsuarioEstado,
    UsuarioOut,
    UsuarioPage,
    UsuarioUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])

Administra = Annotated[UsuarioAutenticado, Depends(require_permission("usuarios:gestionar"))]


@router.get("/roles", response_model=list[RolItem], summary="Roles asignables")
def listar_roles(db: DBSession, _usuario: Administra) -> list[RolItem]:
    return user_service.listar_roles(db)


@router.get(
    "",
    response_model=UsuarioPage,
    summary="Listar usuarios",
    description="Requiere `usuarios:gestionar`. Filtros por texto (correo/nombre), estado y rol.",
)
def listar_usuarios(
    db: DBSession,
    _usuario: Administra,
    q: str | None = None,
    activo: bool | None = None,
    rol: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UsuarioPage:
    return user_service.listar(db, q=q, activo=activo, rol=rol, limit=limit, offset=offset)


@router.post(
    "",
    response_model=UsuarioOut,
    status_code=201,
    summary="Crear usuario",
    description=(
        "409 `EMAIL_DUPLICADO`; 400 `ROL_INVALIDO`, `RUTA_INVALIDA` o `PROVEEDOR_REQUERIDO`."
    ),
)
def crear_usuario(db: DBSession, _usuario: Administra, datos: UsuarioCreate) -> UsuarioOut:
    return user_service.crear(db, datos)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioOut,
    summary="Actualizar usuario (parcial)",
    description=(
        "Edita nombre, contraseña, roles y rutas comerciales. 404 `USUARIO_NO_ENCONTRADO`; "
        "409 `ULTIMO_ADMIN` / `AUTOMODIFICACION_NO_PERMITIDA` al retirar el rol Admin."
    ),
)
def actualizar_usuario(
    db: DBSession, actor: Administra, usuario_id: UUID, datos: UsuarioUpdate
) -> UsuarioOut:
    return user_service.actualizar(db, usuario_id, datos, actor.id)


@router.patch(
    "/{usuario_id}/status",
    response_model=UsuarioOut,
    summary="Activar / desactivar usuario",
    description="Un usuario inactivo no puede iniciar sesión. No permite autodesactivarse.",
)
def cambiar_estado_usuario(
    db: DBSession, actor: Administra, usuario_id: UUID, datos: UsuarioEstado
) -> UsuarioOut:
    return user_service.cambiar_estado(db, usuario_id, datos.activo, actor.id)
