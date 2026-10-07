"""Consultas de usuarios para autenticación: carga de credenciales, roles y permisos."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, or_, select, true, update
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import NombreRol
from app.domain.models.auth import Rol, Usuario
from app.domain.models.catalog import Ruta


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


def proveedor_id_de(db: Session, usuario_id: uuid.UUID) -> uuid.UUID | None:
    """`proveedor_id` de un usuario con rol Proveedor (aislamiento por fila)."""
    return db.scalar(select(Usuario.proveedor_id).where(Usuario.id == usuario_id))


# ------------------------------------------------------------------ gestión administrativa
def obtener_por_id(db: Session, usuario_id: uuid.UUID) -> Usuario | None:
    return db.execute(
        select(Usuario).where(Usuario.id == usuario_id).options(selectinload(Usuario.roles))
    ).scalar_one_or_none()


def existe_email(db: Session, email: str) -> bool:
    stmt = (
        select(func.count()).select_from(Usuario).where(func.lower(Usuario.email) == email.lower())
    )
    return (db.scalar(stmt) or 0) > 0


def listar(
    db: Session,
    *,
    q: str | None,
    activo: bool | None,
    rol: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Usuario], int]:
    filtros = []
    if q:
        patron = f"%{q.strip().lower()}%"
        filtros.append(
            or_(
                func.lower(Usuario.email).like(patron),
                func.lower(Usuario.nombre_completo).like(patron),
            )
        )
    if activo is not None:
        filtros.append(Usuario.activo.is_(activo))
    if rol:
        filtros.append(Usuario.roles.any(Rol.nombre == rol))
    total = db.scalar(select(func.count()).select_from(Usuario).where(*filtros)) or 0
    usuarios = db.scalars(
        select(Usuario)
        .where(*filtros)
        .options(selectinload(Usuario.roles))
        .order_by(func.lower(Usuario.nombre_completo), Usuario.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return usuarios, total


def listar_roles(db: Session) -> Sequence[Rol]:
    return db.scalars(select(Rol).order_by(Rol.id)).all()


def roles_por_nombre(db: Session, nombres: Iterable[str]) -> dict[str, Rol]:
    return {r.nombre: r for r in db.scalars(select(Rol).where(Rol.nombre.in_(set(nombres))))}


def agregar(db: Session, usuario: Usuario) -> Usuario:
    db.add(usuario)
    db.flush()
    return usuario


def contar_admins_activos(db: Session, *, excluyendo: uuid.UUID | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(Usuario)
        .where(Usuario.activo.is_(True), Usuario.roles.any(Rol.nombre == NombreRol.ADMINISTRADOR))
    )
    if excluyendo is not None:
        stmt = stmt.where(Usuario.id != excluyendo)
    return db.scalar(stmt) or 0


def rutas_de(db: Session, usuario_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[Ruta]]:
    """`vendedor_id -> rutas` (la asignación vive en `rutas.vendedor_id`)."""
    ids = set(usuario_ids)
    agrupadas: dict[uuid.UUID, list[Ruta]] = {i: [] for i in ids}
    if ids:
        for ruta in db.scalars(select(Ruta).where(Ruta.vendedor_id.in_(ids)).order_by(Ruta.codigo)):
            agrupadas[ruta.vendedor_id].append(ruta)
    return agrupadas


def rutas_por_ids(db: Session, ruta_ids: Iterable[uuid.UUID]) -> Sequence[Ruta]:
    return db.scalars(select(Ruta).where(Ruta.id.in_(set(ruta_ids)))).all()


def asignar_rutas(db: Session, usuario_id: uuid.UUID, ruta_ids: Iterable[uuid.UUID]) -> None:
    """Deja al usuario exactamente con `ruta_ids` (libera las demás; una ruta = un vendedor)."""
    ids = set(ruta_ids)
    db.execute(
        update(Ruta)
        .where(Ruta.vendedor_id == usuario_id, Ruta.id.not_in(ids) if ids else true())
        .values(vendedor_id=None)
    )
    if ids:
        db.execute(update(Ruta).where(Ruta.id.in_(ids)).values(vendedor_id=usuario_id))
    db.flush()
