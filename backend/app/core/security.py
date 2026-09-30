"""Hashing de contraseñas (bcrypt) y emisión/verificación de JWT (`sub`, `roles`, `perms`)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, sub: str, roles: list[str], perms: list[str]) -> tuple[str, int]:
    """Devuelve `(token, expires_in_segundos)`."""
    settings = get_settings()
    expires_in = settings.jwt_expire_minutes * 60
    ahora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "roles": roles,
        "perms": perms,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Lanza `jwt.ExpiredSignatureError` / `jwt.InvalidTokenError` si el token no es válido."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
