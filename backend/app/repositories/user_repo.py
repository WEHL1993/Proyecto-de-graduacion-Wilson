"""Consultas de usuarios para autenticación: carga de credenciales, roles y permisos."""

import uuid
from collections.abc import Iterable

from sqlalchemy import func, or_, select
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


def mapear_por_identificador(db: Session, identificadores: Iterable[str]) -> dict[str, uuid.UUID]:
    """`email o nombre completo en minúsculas -> usuarios.id` (vendedores citados en el ETL)."""
    buscados = {i.strip().lower() for i in identificadores}
    if not buscados:
        return {}
    stmt = select(Usuario.id, Usuario.email, Usuario.nombre_completo).where(
        or_(
            func.lower(Usuario.email).in_(buscados),
            func.lower(Usuario.nombre_completo).in_(buscados),
        )
    )
    resueltos: dict[str, uuid.UUID] = {}
    for usuario_id, email, nombre in db.execute(stmt):
        for clave in (email.lower(), nombre.lower()):
            if clave in buscados:
                resueltos.setdefault(clave, usuario_id)
    return resueltos
