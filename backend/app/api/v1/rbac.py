"""Matriz de roles, permisos y pantallas (`/rbac`, permiso `roles:gestionar`, ADR-19).

Sin reglas de negocio: delega en `rbac_service`. Todo se lee y escribe en la BD."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DBSession, require_permission
from app.schemas.auth import UsuarioAutenticado
from app.schemas.rbac import (
    AccesoUsuario,
    MatrizAcceso,
    RolMatriz,
    RolPermisosUpdate,
    RolUpdate,
)
from app.services import rbac_service

router = APIRouter(prefix="/rbac", tags=["RBAC"])

Administra = Annotated[UsuarioAutenticado, Depends(require_permission("roles:gestionar"))]


@router.get(
    "/matrix",
    response_model=MatrizAcceso,
    summary="Matriz de roles, permisos y pantallas",
    description="Requiere `roles:gestionar`. Todo proviene de las tablas RBAC.",
)
def matriz(db: DBSession, _usuario: Administra) -> MatrizAcceso:
    return rbac_service.consultar_matriz(db)


@router.put(
    "/roles/{rol_id}/permissions",
    response_model=RolMatriz,
    summary="Reemplazar los permisos de un rol",
    description=(
        "Guarda el conjunto completo. 404 `ROL_NO_ENCONTRADO`; 400 `PERMISO_INVALIDO`; "
        "409 `ROL_SISTEMA_PROTEGIDO` (Administrador)."
    ),
)
def reemplazar_permisos(
    db: DBSession, _usuario: Administra, rol_id: int, datos: RolPermisosUpdate
) -> RolMatriz:
    return rbac_service.actualizar_permisos_rol(db, rol_id, datos)


@router.patch(
    "/roles/{rol_id}",
    response_model=RolMatriz,
    summary="Activar/desactivar un rol y ajustar su presentación",
    description=(
        "404 `ROL_NO_ENCONTRADO`; 400 `PANTALLA_INVALIDA`; 409 `ROL_SISTEMA_PROTEGIDO` o "
        "`ROL_CON_USUARIOS` (usuarios activos que quedarían sin ningún rol activo)."
    ),
)
def actualizar_rol(db: DBSession, _usuario: Administra, rol_id: int, datos: RolUpdate) -> RolMatriz:
    return rbac_service.actualizar_rol(db, rol_id, datos)


@router.get(
    "/users/{usuario_id}/access",
    response_model=AccesoUsuario,
    summary="Pantallas autorizadas de un usuario",
    description="Vista «ver como»: cada pantalla con el permiso que la habilita.",
)
def acceso_de_usuario(db: DBSession, _usuario: Administra, usuario_id: UUID) -> AccesoUsuario:
    return rbac_service.consultar_acceso_usuario(db, usuario_id)
