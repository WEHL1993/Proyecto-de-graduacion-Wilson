"""Personal de ruta (M02): CRUD con baja lógica. Un empleado NO es un usuario del sistema;
`usuario_id` es un vínculo opcional y único."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.models.catalog import Empleado
from app.repositories import empleado_repo, ruta_repo
from app.schemas.equipos import EmpleadoCreate, EmpleadoOut, EmpleadoPage, EmpleadoUpdate
from app.services.bitacora_service import auditar


def _dto(e: Empleado) -> EmpleadoOut:
    return EmpleadoOut(
        id=e.id,
        nombre_completo=e.nombre_completo,
        usuario_id=e.usuario_id,
        activo=e.activo,
        creado_en=e.creado_en,
    )


def _vinculado() -> AppError:
    return AppError(
        "USUARIO_YA_VINCULADO", "Ese usuario ya está vinculado a otro empleado.", status_code=409
    )


def _obtener(db: Session, empleado_id: uuid.UUID, *, bloquear: bool = False) -> Empleado:
    empleado = empleado_repo.obtener(db, empleado_id, bloquear=bloquear)
    if empleado is None:
        raise AppError("EMPLEADO_NO_ENCONTRADO", "El empleado no existe.", status_code=404)
    return empleado


def _validar_usuario(db: Session, usuario_id: uuid.UUID | None, propio: uuid.UUID | None) -> None:
    if usuario_id is None:
        return
    if not ruta_repo.usuario_existe(db, usuario_id):
        raise AppError("USUARIO_NO_ENCONTRADO", "El usuario indicado no existe.", status_code=404)
    otro = empleado_repo.por_usuario(db, usuario_id)
    if otro is not None and otro.id != propio:
        raise _vinculado()


@auditar
def listar(
    db: Session, *, activo: bool | None, q: str | None, limit: int, offset: int
) -> EmpleadoPage:
    filas, total = empleado_repo.listar(db, activo=activo, q=q, limit=limit, offset=offset)
    return EmpleadoPage(items=[_dto(e) for e in filas], total=total, limit=limit, offset=offset)


@auditar
def obtener(db: Session, empleado_id: uuid.UUID) -> EmpleadoOut:
    return _dto(_obtener(db, empleado_id))


@auditar
def crear(db: Session, datos: EmpleadoCreate, actor_id: uuid.UUID) -> EmpleadoOut:
    _validar_usuario(db, datos.usuario_id, None)
    try:
        empleado = empleado_repo.crear(
            db, {"nombre_completo": datos.nombre_completo.strip(), "usuario_id": datos.usuario_id}
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _vinculado() from exc
    return _dto(empleado)


@auditar
def actualizar(
    db: Session, empleado_id: uuid.UUID, datos: EmpleadoUpdate, actor_id: uuid.UUID
) -> EmpleadoOut:
    empleado = _obtener(db, empleado_id, bloquear=True)
    if datos.nombre_completo is not None:
        empleado.nombre_completo = datos.nombre_completo.strip()
    if "usuario_id" in datos.model_fields_set:  # None explícito = desvincular
        _validar_usuario(db, datos.usuario_id, empleado.id)
        empleado.usuario_id = datos.usuario_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _vinculado() from exc
    return _dto(empleado)


@auditar
def dar_de_baja(db: Session, empleado_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Baja lógica idempotente. 409 `EMPLEADO_EN_USO` si integra el equipo vigente de una ruta."""
    empleado = _obtener(db, empleado_id, bloquear=True)
    if not empleado.activo:
        return
    rutas = empleado_repo.rutas_vigentes_de(db, empleado.id)
    if rutas:
        raise AppError(
            "EMPLEADO_EN_USO",
            "No se puede dar de baja: el empleado integra el equipo vigente de una ruta.",
            status_code=409,
            detalle={"rutas": [str(r) for r in rutas]},
        )
    empleado.activo = False
    db.commit()


@auditar
def reactivar(db: Session, empleado_id: uuid.UUID, actor_id: uuid.UUID) -> EmpleadoOut:
    empleado = _obtener(db, empleado_id, bloquear=True)
    if not empleado.activo:
        empleado.activo = True
        db.commit()
    return _dto(empleado)
