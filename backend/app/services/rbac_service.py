"""RBAC en base de datos (ADR-19): acceso vigente, menú, matriz rol×permiso y activación de roles.

La BD es la fuente de verdad: roles, permisos, `roles_permisos` y `pantallas_permisos` se
consultan y editan aquí; ningún permiso por rol vive en el código."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.models.auth import Pantalla, Rol, Usuario
from app.repositories import rbac_repo
from app.schemas.rbac import (
    AccesoSesion,
    AccesoUsuario,
    MatrizAcceso,
    PantallaAcceso,
    PantallaMatriz,
    PantallaMenu,
    PermisoMatriz,
    RolMatriz,
    RolPermisosUpdate,
    RolUpdate,
)
from app.services.bitacora_service import auditar


# ------------------------------------------------------------------ helpers
def resolver_acceso(db: Session, usuario_id: uuid.UUID) -> tuple[list[str], list[str]]:
    """Roles y permisos vigentes del usuario según la BD (helper por petición, no se audita).

    401 si la cuenta ya no existe o fue desactivada: el token firmado deja de valer."""
    acceso = rbac_repo.acceso_de_usuario(db, usuario_id)
    if acceso is None:
        raise AppError("SESION_INVALIDA", "La cuenta no existe o está inactiva.", status_code=401)
    return acceso


def _menu(p: Pantalla) -> PantallaMenu:
    return PantallaMenu(
        clave=p.clave,
        etiqueta=p.etiqueta,
        ruta=p.ruta,
        ruta_prefijo=p.ruta_prefijo,
        grupo=p.grupo,
        orden=p.orden,
    )


def _rol_matriz(rol: Rol, usuarios: dict[int, int], claves: dict[int, str]) -> RolMatriz:
    return RolMatriz(
        id=rol.id,
        nombre=rol.nombre,
        descripcion=rol.descripcion,
        activo=rol.activo,
        es_sistema=rol.es_sistema,
        requiere_proveedor=rol.requiere_proveedor,
        color=rol.color,
        pantalla_inicio=claves.get(rol.pantalla_inicio_id) if rol.pantalla_inicio_id else None,
        total_usuarios=usuarios.get(rol.id, 0),
        permisos=sorted(p.codigo for p in rol.permisos),
    )


def _obtener_rol(db: Session, rol_id: int) -> Rol:
    rol = rbac_repo.obtener_rol(db, rol_id)
    if rol is None:
        raise AppError("ROL_NO_ENCONTRADO", "El rol no existe.", status_code=404)
    return rol


def _rol_dto(db: Session, rol: Rol) -> RolMatriz:
    claves = {p.id: p.clave for p in rbac_repo.listar_pantallas(db)}
    return _rol_matriz(rol, rbac_repo.usuarios_por_rol(db), claves)


# ------------------------------------------------------------------ sesión
@auditar
def consultar_sesion(db: Session, usuario_id: uuid.UUID) -> AccesoSesion:
    """Roles, permisos y menú vigentes de quien consulta (`GET /auth/me`)."""
    roles, permisos = resolver_acceso(db, usuario_id)
    return construir_sesion(db, usuario_id, roles, permisos)


def construir_sesion(
    db: Session, usuario_id: uuid.UUID, roles: list[str], permisos: list[str]
) -> AccesoSesion:
    usuario = db.get(Usuario, usuario_id)
    pantallas = rbac_repo.pantallas_autorizadas(db, permisos)
    inicio = rbac_repo.pantalla_inicio_de(db, usuario_id)
    autorizadas = {p.id for p in pantallas}
    if inicio is not None and inicio.id not in autorizadas:
        inicio = None  # configurada, pero el usuario ya no puede verla
    inicio = inicio or (pantallas[0] if pantallas else None)
    return AccesoSesion(
        id=usuario_id,
        nombre_completo=usuario.nombre_completo if usuario else "",
        roles=roles,
        permisos=permisos,
        menu=[_menu(p) for p in pantallas],
        pantalla_inicio=inicio.ruta if inicio else None,
        debe_cambiar_password=usuario.debe_cambiar_password if usuario else False,
    )


# ------------------------------------------------------------------ matriz
@auditar
def consultar_matriz(db: Session) -> MatrizAcceso:
    pantallas = rbac_repo.listar_pantallas(db)
    claves = {p.id: p.clave for p in pantallas}
    usuarios = rbac_repo.usuarios_por_rol(db)
    return MatrizAcceso(
        roles=[_rol_matriz(r, usuarios, claves) for r in rbac_repo.listar_roles(db)],
        permisos=[
            PermisoMatriz(
                id=p.id,
                codigo=p.codigo,
                descripcion=p.descripcion,
                modulo=p.modulo,
                activo=p.activo,
            )
            for p in rbac_repo.listar_permisos(db)
        ],
        pantallas=[
            PantallaMatriz(
                id=p.id,
                clave=p.clave,
                etiqueta=p.etiqueta,
                ruta=p.ruta,
                grupo=p.grupo,
                orden=p.orden,
                activo=p.activo,
                permisos=sorted(x.codigo for x in p.permisos),
            )
            for p in pantallas
        ],
    )


@auditar
def actualizar_permisos_rol(db: Session, rol_id: int, datos: RolPermisosUpdate) -> RolMatriz:
    rol = _obtener_rol(db, rol_id)
    if rol.es_sistema:
        raise AppError(
            "ROL_SISTEMA_PROTEGIDO",
            f"Los permisos del rol {rol.nombre} no se pueden modificar.",
            status_code=409,
        )
    codigos = set(datos.permisos)
    encontrados = rbac_repo.permisos_por_codigo(db, codigos)
    faltantes = sorted(codigos - encontrados.keys())
    if faltantes:
        raise AppError("PERMISO_INVALIDO", f"Permiso(s) inexistente(s): {', '.join(faltantes)}.")
    rol.permisos = [encontrados[c] for c in sorted(codigos)]
    db.commit()
    db.refresh(rol)
    return _rol_dto(db, rol)


@auditar
def actualizar_rol(db: Session, rol_id: int, datos: RolUpdate) -> RolMatriz:
    rol = _obtener_rol(db, rol_id)
    campos = datos.model_fields_set

    if datos.activo is not None and datos.activo != rol.activo:
        if not datos.activo:
            if rol.es_sistema:
                raise AppError(
                    "ROL_SISTEMA_PROTEGIDO",
                    f"El rol {rol.nombre} no se puede desactivar.",
                    status_code=409,
                )
            huerfanos = rbac_repo.usuarios_activos_sin_otro_rol(db, rol.id)
            if huerfanos:
                raise AppError(
                    "ROL_CON_USUARIOS",
                    f"{huerfanos} usuario(s) activo(s) se quedarían sin acceso: "
                    "asígneles otro rol antes de desactivar este.",
                    status_code=409,
                )
        rol.activo = datos.activo
    if "descripcion" in campos:
        rol.descripcion = datos.descripcion
    if datos.color is not None:
        rol.color = datos.color.value
    if "pantalla_inicio" in campos:
        if datos.pantalla_inicio is None:
            rol.pantalla_inicio_id = None
        else:
            pantalla = rbac_repo.pantalla_por_clave(db, datos.pantalla_inicio)
            if pantalla is None:
                raise AppError("PANTALLA_INVALIDA", "La pantalla de inicio no existe.")
            rol.pantalla_inicio_id = pantalla.id
    db.commit()
    db.refresh(rol)
    return _rol_dto(db, rol)


# ------------------------------------------------------------------ acceso por usuario
@auditar
def consultar_acceso_usuario(db: Session, usuario_id: uuid.UUID) -> AccesoUsuario:
    """Qué pantallas ve un usuario y por qué permiso (vista «ver como»)."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise AppError("USUARIO_NO_ENCONTRADO", "El usuario no existe.", status_code=404)
    acceso = rbac_repo.acceso_de_usuario(db, usuario_id)
    roles, permisos = acceso if acceso is not None else ([], [])  # inactivo: sin acceso
    propios = set(permisos)
    return AccesoUsuario(
        usuario_id=usuario.id,
        nombre_completo=usuario.nombre_completo,
        activo=usuario.activo,
        roles=roles,
        permisos=permisos,
        pantallas=[
            PantallaAcceso(
                clave=p.clave,
                etiqueta=p.etiqueta,
                ruta=p.ruta,
                grupo=p.grupo,
                autorizada=p.activo and bool(propios & {x.codigo for x in p.permisos}),
                via_permisos=sorted(propios & {x.codigo for x in p.permisos}),
            )
            for p in rbac_repo.listar_pantallas(db)
        ],
    )
