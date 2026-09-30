"""Verificación de permisos RBAC (`recurso:accion`), ADR-05.

Los permisos viajan en el JWT (`perms`), por lo que la verificación no consulta la BD en
cada request. `api/deps.py` expone esto como la dependencia `require_permission`.
"""

from app.core.errors import AppError
from app.schemas.auth import UsuarioAutenticado


def verificar_permiso(usuario: UsuarioAutenticado, permiso: str) -> None:
    if permiso not in usuario.permisos:
        raise AppError(
            codigo="PERMISO_DENEGADO",
            mensaje=f"El usuario no cuenta con el permiso requerido: '{permiso}'.",
            status_code=403,
        )
