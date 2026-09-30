"""Dependencias transversales de la API: sesión de BD, usuario actual y guardas RBAC."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.rbac import verificar_permiso
from app.core.security import decode_access_token
from app.schemas.auth import UsuarioAutenticado

DBSession = Annotated[Session, Depends(get_db)]

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UsuarioAutenticado:
    """Decodifica el JWT del header `Authorization: Bearer`. 401 si falta o no es válido."""
    if credenciales is None:
        raise AppError("NO_AUTENTICADO", "Falta el token de autenticación.", status_code=401)
    try:
        payload = decode_access_token(credenciales.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise AppError("TOKEN_EXPIRADO", "El token ha expirado.", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError("TOKEN_INVALIDO", "El token es inválido.", status_code=401) from exc

    return UsuarioAutenticado(
        id=payload["sub"],
        roles=payload.get("roles", []),
        permisos=payload.get("perms", []),
    )


CurrentUser = Annotated[UsuarioAutenticado, Depends(get_current_user)]


def require_permission(permiso: str) -> Callable[[UsuarioAutenticado], UsuarioAutenticado]:
    """Fábrica de dependencia: 403 `PERMISO_DENEGADO` si el usuario autenticado no lo tiene."""

    def _dependencia(usuario: CurrentUser) -> UsuarioAutenticado:
        verificar_permiso(usuario, permiso)
        return usuario

    return _dependencia
