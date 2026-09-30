"""Consultas de usuarios para autenticación: carga de credenciales, roles y permisos."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.models.auth import Rol, Usuario


def obtener_por_email(db: Session, email: str) -> Usuario | None:
    """Carga el usuario con roles y permisos precargados (evita N+1 al construir el JWT)."""
    stmt = (
        select(Usuario)
        .where(Usuario.email == email)
        .options(selectinload(Usuario.roles).selectinload(Rol.permisos))
    )
    return db.execute(stmt).scalar_one_or_none()
