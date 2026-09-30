"""Pruebas sin base de datos: hashing, JWT y dependencias de autenticación/RBAC.

Cubre TC-AUTH-03 (token vencido) a nivel de dependencia, sin requerir un endpoint
protegido concreto.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.api.deps import get_current_user, require_permission
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import UsuarioAutenticado


def test_hash_password_no_es_texto_plano_y_verifica_correctamente():
    hash_ = hash_password("ClaveSegura123")
    assert hash_ != "ClaveSegura123"
    assert verify_password("ClaveSegura123", hash_)
    assert not verify_password("otra-clave", hash_)


def test_create_access_token_incluye_claims_y_es_decodificable():
    token, expires_in = create_access_token(
        sub="11111111-1111-1111-1111-111111111111",
        roles=["Ventas"],
        perms=["carga_ruta:generar"],
    )
    assert expires_in == get_settings().jwt_expire_minutes * 60

    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["roles"] == ["Ventas"]
    assert payload["perms"] == ["carga_ruta:generar"]
    assert payload["exp"] > datetime.now(UTC).timestamp()


def _credenciales(token: str):
    from fastapi.security import HTTPAuthorizationCredentials

    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_sin_token_lanza_401():
    with pytest.raises(AppError) as exc_info:
        get_current_user(None)
    assert exc_info.value.status_code == 401
    assert exc_info.value.codigo == "NO_AUTENTICADO"


def test_get_current_user_token_invalido_lanza_401():
    with pytest.raises(AppError) as exc_info:
        get_current_user(_credenciales("token-mal-formado"))
    assert exc_info.value.status_code == 401
    assert exc_info.value.codigo == "TOKEN_INVALIDO"


def test_get_current_user_token_vencido_lanza_401():
    """TC-AUTH-03: JWT con `exp` pasado debe rechazarse con 401, sin cuerpo con datos."""
    settings = get_settings()
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "roles": ["Ventas"],
        "perms": [],
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    token_vencido = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(AppError) as exc_info:
        get_current_user(_credenciales(token_vencido))
    assert exc_info.value.status_code == 401
    assert exc_info.value.codigo == "TOKEN_EXPIRADO"


def test_get_current_user_token_valido_devuelve_usuario():
    token, _ = create_access_token(
        sub="11111111-1111-1111-1111-111111111111", roles=["Admin"], perms=["usuarios:gestionar"]
    )
    usuario = get_current_user(_credenciales(token))
    assert isinstance(usuario, UsuarioAutenticado)
    assert usuario.roles == ["Admin"]
    assert usuario.permisos == ["usuarios:gestionar"]


def test_require_permission_deniega_con_403_si_falta_el_permiso():
    usuario = UsuarioAutenticado(
        id="11111111-1111-1111-1111-111111111111", roles=["Bodega"], permisos=["inventario:leer"]
    )
    dependencia = require_permission("ml:reentrenar")
    with pytest.raises(AppError) as exc_info:
        dependencia(usuario)
    assert exc_info.value.status_code == 403
    assert exc_info.value.codigo == "PERMISO_DENEGADO"


def test_require_permission_permite_si_el_usuario_lo_tiene():
    usuario = UsuarioAutenticado(
        id="11111111-1111-1111-1111-111111111111", roles=["Gerente"], permisos=["ml:reentrenar"]
    )
    dependencia = require_permission("ml:reentrenar")
    assert dependencia(usuario) is usuario
