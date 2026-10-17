"""Consultas de RBAC (ADR-19): acceso vigente de un usuario, matriz rol×permiso y pantallas."""

import uuid
from collections.abc import Sequence

from sqlalchemy import distinct, exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.models.auth import (
    Pantalla,
    PantallaPermiso,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)


# ------------------------------------------------------------------ acceso de un usuario
def acceso_de_usuario(db: Session, usuario_id: uuid.UUID) -> tuple[list[str], list[str]] | None:
    """`(roles, permisos)` vigentes en la BD, o `None` si el usuario no existe o está inactivo.

    Solo cuentan roles y permisos activos: desactivarlos retira el acceso de inmediato."""
    activo = db.scalar(select(Usuario.activo).where(Usuario.id == usuario_id))
    if not activo:
        return None
    roles = db.scalars(
        select(Rol.nombre)
        .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
        .where(UsuarioRol.usuario_id == usuario_id, Rol.activo.is_(True))
        .order_by(Rol.nombre)
    ).all()
    permisos = db.scalars(
        select(distinct(Permiso.codigo))
        .join(RolPermiso, RolPermiso.permiso_id == Permiso.id)
        .join(Rol, Rol.id == RolPermiso.rol_id)
        .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
        .where(
            UsuarioRol.usuario_id == usuario_id,
            Rol.activo.is_(True),
            Permiso.activo.is_(True),
        )
        .order_by(Permiso.codigo)
    ).all()
    return list(roles), list(permisos)


def pantallas_autorizadas(db: Session, permisos: Sequence[str]) -> list[Pantalla]:
    """Pantallas activas que se habilitan con ALGUNO de los permisos dados, en orden de menú."""
    if not permisos:
        return []
    stmt = (
        select(Pantalla)
        .where(
            Pantalla.activo.is_(True),
            exists().where(
                PantallaPermiso.pantalla_id == Pantalla.id,
                PantallaPermiso.permiso_id == Permiso.id,
                Permiso.codigo.in_(set(permisos)),
            ),
        )
        .order_by(Pantalla.orden, Pantalla.id)
    )
    return list(db.scalars(stmt))


def pantalla_inicio_de(db: Session, usuario_id: uuid.UUID) -> Pantalla | None:
    """Pantalla de inicio del primer rol activo del usuario que tenga una configurada."""
    return db.scalars(
        select(Pantalla)
        .join(Rol, Rol.pantalla_inicio_id == Pantalla.id)
        .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
        .where(UsuarioRol.usuario_id == usuario_id, Rol.activo.is_(True), Pantalla.activo.is_(True))
        .order_by(Rol.id)
    ).first()


# ------------------------------------------------------------------ matriz
def listar_roles(db: Session) -> Sequence[Rol]:
    return db.scalars(select(Rol).options(selectinload(Rol.permisos)).order_by(Rol.id)).all()


def listar_permisos(db: Session) -> Sequence[Permiso]:
    return db.scalars(select(Permiso).order_by(Permiso.modulo, Permiso.codigo)).all()


def listar_pantallas(db: Session) -> Sequence[Pantalla]:
    return db.scalars(
        select(Pantalla).options(selectinload(Pantalla.permisos)).order_by(Pantalla.orden)
    ).all()


def usuarios_por_rol(db: Session) -> dict[int, int]:
    """`rol_id -> cantidad de usuarios` asignados."""
    filas = db.execute(select(UsuarioRol.rol_id, func.count()).group_by(UsuarioRol.rol_id)).all()
    return {rol_id: total for rol_id, total in filas}


def obtener_rol(db: Session, rol_id: int) -> Rol | None:
    return db.scalars(
        select(Rol).where(Rol.id == rol_id).options(selectinload(Rol.permisos))
    ).one_or_none()


def permisos_por_codigo(db: Session, codigos: set[str]) -> dict[str, Permiso]:
    return {p.codigo: p for p in db.scalars(select(Permiso).where(Permiso.codigo.in_(codigos)))}


def pantalla_por_clave(db: Session, clave: str) -> Pantalla | None:
    return db.scalars(select(Pantalla).where(Pantalla.clave == clave)).one_or_none()


def usuarios_activos_sin_otro_rol(db: Session, rol_id: int) -> int:
    """Usuarios activos que quedarían sin ningún rol activo si se desactiva `rol_id`."""
    otro_activo = (
        select(UsuarioRol.rol_id)
        .join(Rol, Rol.id == UsuarioRol.rol_id)
        .where(
            UsuarioRol.usuario_id == Usuario.id,
            UsuarioRol.rol_id != rol_id,
            Rol.activo.is_(True),
        )
        .exists()
    )
    stmt = (
        select(func.count())
        .select_from(Usuario)
        .where(
            Usuario.activo.is_(True),
            Usuario.roles.any(Rol.id == rol_id),
            ~otro_activo,
        )
    )
    return db.scalar(stmt) or 0
