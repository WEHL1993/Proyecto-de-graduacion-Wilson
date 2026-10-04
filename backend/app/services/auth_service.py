"""Caso de uso de autenticación: login, validación de estado y emisión de JWT (TC-AUTH-*)."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_access_token, verify_password
from app.repositories import user_repo
from app.schemas.auth import LoginRequest, TokenResponse, UsuarioToken
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

    roles = sorted({rol.nombre for rol in usuario.roles})
    permisos = sorted({permiso.codigo for rol in usuario.roles for permiso in rol.permisos})

    access_token, expires_in = create_access_token(sub=str(usuario.id), roles=roles, perms=permisos)

    usuario.ultimo_login = datetime.now(UTC)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        usuario=UsuarioToken(
            id=usuario.id,
            nombre_completo=usuario.nombre_completo,
            roles=roles,
            permisos=permisos,
        ),
    )
