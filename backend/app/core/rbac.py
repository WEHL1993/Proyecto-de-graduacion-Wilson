"""Verificación de permisos RBAC (`recurso:accion`), ADR-05.

Los permisos viajan en el JWT (`perms`), por lo que la verificación no consulta la BD en
cada request. `api/deps.py` expone esto como la dependencia `require_permission`.
"""

import logging

from app.core.errors import AppError
from app.schemas.auth import UsuarioAutenticado

auditoria = logging.getLogger("app.auditoria")


def verificar_permiso(usuario: UsuarioAutenticado, permiso: str) -> None:
    if permiso not in usuario.permisos:
        auditoria.warning(
            "PERMISO_DENEGADO usuario=%s roles=%s permiso=%s", usuario.id, usuario.roles, permiso
        )
        raise AppError(
            codigo="PERMISO_DENEGADO",
            mensaje=f"El usuario no cuenta con el permiso requerido: '{permiso}'.",
            status_code=403,
        )
