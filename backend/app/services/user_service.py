"""Gestión administrativa de usuarios: alta, edición, asignación de roles/rutas y estado."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password
from app.domain.enums import NombreRol
from app.domain.models.auth import Rol, Usuario
from app.domain.models.catalog import Ruta
from app.repositories import user_repo
from app.schemas.users import (
    RolItem,
    RutaAsignada,
    UsuarioCreate,
    UsuarioOut,
    UsuarioPage,
    UsuarioUpdate,
)
from app.services.bitacora_service import auditar

ROL_PROVEEDOR = NombreRol.PROVEEDOR
ROL_ADMIN = NombreRol.ADMINISTRADOR


def _a_dto(usuario: Usuario, rutas: list[Ruta]) -> UsuarioOut:
    return UsuarioOut(
        id=usuario.id,
        email=usuario.email,
        nombre_completo=usuario.nombre_completo,
        activo=usuario.activo,
        roles=sorted(r.nombre for r in usuario.roles),
        rutas=[RutaAsignada(id=r.id, codigo=r.codigo, nombre=r.nombre) for r in rutas],
        proveedor_id=usuario.proveedor_id,
        ultimo_login=usuario.ultimo_login,
        creado_en=usuario.creado_en,
    )


def _dto(db: Session, usuario: Usuario) -> UsuarioOut:
    return _a_dto(usuario, user_repo.rutas_de(db, [usuario.id])[usuario.id])


def _resolver_roles(db: Session, nombres: list[str]) -> list[Rol]:
    encontrados = user_repo.roles_por_nombre(db, nombres)
    faltantes = sorted(set(nombres) - encontrados.keys())
    if faltantes:
        raise AppError("ROL_INVALIDO", f"Rol(es) inexistente(s): {', '.join(faltantes)}.")
    return [encontrados[n] for n in dict.fromkeys(nombres)]


def _validar_rutas(db: Session, ruta_ids: list[uuid.UUID]) -> None:
    ids = set(ruta_ids)
    if len(user_repo.rutas_por_ids(db, ids)) != len(ids):
        raise AppError("RUTA_INVALIDA", "Una o más rutas asignadas no existen.")


def _validar_proveedor(roles: list[Rol], proveedor_id: uuid.UUID | None) -> uuid.UUID | None:
    es_proveedor = any(r.nombre == ROL_PROVEEDOR for r in roles)
    if es_proveedor and proveedor_id is None:
        raise AppError(
            "PROVEEDOR_REQUERIDO", "El rol Proveedor exige asociar un proveedor_id (aislamiento)."
        )
    return proveedor_id if es_proveedor else None


def _obtener(db: Session, usuario_id: uuid.UUID) -> Usuario:
    usuario = user_repo.obtener_por_id(db, usuario_id)
    if usuario is None:
        raise AppError("USUARIO_NO_ENCONTRADO", "El usuario no existe.", status_code=404)
    return usuario


def _proteger_admin(db: Session, usuario: Usuario, actor_id: uuid.UUID, accion: str) -> None:
    """Impide que el administrador se quite el acceso o deje el sistema sin administradores."""
    if usuario.id == actor_id:
        raise AppError(
            "AUTOMODIFICACION_NO_PERMITIDA",
            f"No puede {accion} de su propia cuenta.",
            status_code=409,
        )
    if user_repo.contar_admins_activos(db, excluyendo=usuario.id) == 0:
        raise AppError(
            "ULTIMO_ADMIN",
            f"No se puede {accion}: es el último administrador activo.",
            status_code=409,
        )


@auditar
def listar_roles(db: Session) -> list[RolItem]:
    return [
        RolItem(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
        for r in user_repo.listar_roles(db)
    ]


@auditar
def listar(
    db: Session, *, q: str | None, activo: bool | None, rol: str | None, limit: int, offset: int
) -> UsuarioPage:
    usuarios, total = user_repo.listar(db, q=q, activo=activo, rol=rol, limit=limit, offset=offset)
    rutas = user_repo.rutas_de(db, [u.id for u in usuarios])
    return UsuarioPage(total=total, usuarios=[_a_dto(u, rutas[u.id]) for u in usuarios])


@auditar
def crear(db: Session, datos: UsuarioCreate) -> UsuarioOut:
    email = str(datos.email).lower()
    if user_repo.existe_email(db, email):
        raise AppError("EMAIL_DUPLICADO", "Ya existe un usuario con ese correo.", status_code=409)
    roles = _resolver_roles(db, datos.roles)
    proveedor_id = _validar_proveedor(roles, datos.proveedor_id)
    _validar_rutas(db, datos.ruta_ids)

    usuario = user_repo.agregar(
        db,
        Usuario(
            email=email,
            password_hash=hash_password(datos.password),
            nombre_completo=datos.nombre_completo.strip(),
            proveedor_id=proveedor_id,
            activo=datos.activo,
            roles=roles,
        ),
    )
    user_repo.asignar_rutas(db, usuario.id, datos.ruta_ids)
    db.commit()
    db.refresh(usuario)
    return _dto(db, usuario)


@auditar
def actualizar(
    db: Session, usuario_id: uuid.UUID, datos: UsuarioUpdate, actor_id: uuid.UUID
) -> UsuarioOut:
    usuario = _obtener(db, usuario_id)
    campos = datos.model_fields_set

    if datos.roles is not None:
        roles = _resolver_roles(db, datos.roles)
        era_admin = any(r.nombre == ROL_ADMIN for r in usuario.roles)
        if era_admin and ROL_ADMIN not in {r.nombre for r in roles}:
            _proteger_admin(db, usuario, actor_id, "quitar el rol Administrador")
        usuario.roles = roles
    if datos.roles is not None or "proveedor_id" in campos:
        nuevo = datos.proveedor_id if "proveedor_id" in campos else usuario.proveedor_id
        usuario.proveedor_id = _validar_proveedor(list(usuario.roles), nuevo)
    if datos.nombre_completo is not None:
        usuario.nombre_completo = datos.nombre_completo.strip()
    if datos.password is not None:
        usuario.password_hash = hash_password(datos.password)
    if datos.ruta_ids is not None:
        _validar_rutas(db, datos.ruta_ids)
        user_repo.asignar_rutas(db, usuario.id, datos.ruta_ids)

    db.commit()
    db.refresh(usuario)
    return _dto(db, usuario)


@auditar
def cambiar_estado(
    db: Session, usuario_id: uuid.UUID, activo: bool, actor_id: uuid.UUID
) -> UsuarioOut:
    usuario = _obtener(db, usuario_id)
    if not activo and usuario.activo:
        if any(r.nombre == ROL_ADMIN for r in usuario.roles):
            _proteger_admin(db, usuario, actor_id, "desactivar la cuenta")
        elif usuario.id == actor_id:
            raise AppError(
                "AUTOMODIFICACION_NO_PERMITIDA",
                "No puede desactivar su propia cuenta.",
                status_code=409,
            )
    usuario.activo = activo
    db.commit()
    db.refresh(usuario)
    return _dto(db, usuario)
