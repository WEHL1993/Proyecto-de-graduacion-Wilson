"""Caso de uso de autenticación: login, validación de estado y emisión de JWT (TC-AUTH-*)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories import user_repo
from app.schemas.auth import CambiarPasswordRequest, LoginRequest, TokenResponse, UsuarioToken
from app.services import rbac_service
from app.services.bitacora_service import auditar

# TC-AUTH-02: el mensaje debe ser idéntico para correo inexistente, contraseña incorrecta
# y usuario inactivo, para no revelar si el correo existe.
_CODIGO_CREDENCIALES_INVALIDAS = "CREDENCIALES_INVALIDAS"
_MENSAJE_CREDENCIALES_INVALIDAS = "El correo o la contraseña son incorrectos."


def _rechazar_credenciales() -> AppError:
    return AppError(
        _CODIGO_CREDENCIALES_INVALIDAS, _MENSAJE_CREDENCIALES_INVALIDAS, status_code=401
    )


@auditar
def login(db: Session, datos: LoginRequest) -> TokenResponse:
    usuario = user_repo.obtener_por_email(db, datos.email)
    if usuario is None or not verify_password(datos.password, usuario.password_hash):
        raise _rechazar_credenciales()
    if not usuario.activo:
        raise _rechazar_credenciales()

    roles, permisos = rbac_service.resolver_acceso(db, usuario.id)  # solo roles/permisos activos

    access_token, expires_in = create_access_token(sub=str(usuario.id), roles=roles, perms=permisos)

    usuario.ultimo_login = datetime.now(UTC)
    db.commit()

    sesion = rbac_service.construir_sesion(db, usuario.id, roles, permisos)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        usuario=UsuarioToken(
            id=usuario.id,
            nombre_completo=usuario.nombre_completo,
            roles=roles,
            permisos=permisos,
            menu=sesion.menu,
            pantalla_inicio=sesion.pantalla_inicio,
            debe_cambiar_password=usuario.debe_cambiar_password,
        ),
    )


@auditar
def cambiar_password(db: Session, usuario_id: uuid.UUID, datos: CambiarPasswordRequest) -> None:
    """El propio usuario reemplaza su contraseña (también la temporal fijada por un admin)."""
    usuario = user_repo.obtener_por_id(db, usuario_id)
    if usuario is None or not usuario.activo:
        raise AppError("NO_AUTENTICADO", "La sesión ya no es válida.", status_code=401)
    if not verify_password(datos.password_actual, usuario.password_hash):
        raise AppError(
            "PASSWORD_ACTUAL_INCORRECTA", "La contraseña actual es incorrecta.", status_code=400
        )
    if datos.password_nueva == datos.password_actual:
        raise AppError(
            "PASSWORD_REPETIDA", "La nueva contraseña debe ser distinta de la actual.", status_code=400
        )
    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.debe_cambiar_password = False
    db.commit()
