"""Gestión administrativa de rutas (M02): alta, edición y activación/desactivación.

`rutas.vendedor_id` conserva su semántica (liquidación y cargas lo leen). El `codigo` queda
fijo tras el alta porque el ETL resuelve la ruta por código o nombre.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import RolEnRuta
from app.domain.models.catalog import Ruta
from app.repositories import empleado_repo, equipo_repo, ruta_repo
from app.schemas.equipos import RutaAdminOut, RutaCreate, RutaUpdate
from app.services.bitacora_service import auditar
from app.services.equipo_service import (
    motivos_incompleto,
    suma_porcentajes,
    validar_vendedor_coherente,
)


def _dto(ruta: Ruta, filas) -> RutaAdminOut:
    return RutaAdminOut(
        id=ruta.id,
        codigo=ruta.codigo,
        nombre=ruta.nombre,
        zona=ruta.zona,
        vendedor_id=ruta.vendedor_id,
        activa=ruta.activa,
        integrantes=len(filas),
        suma_porcentaje=suma_porcentajes(filas),
        equipo_completo=not motivos_incompleto(filas),
    )


def _dto_de(db: Session, ruta: Ruta) -> RutaAdminOut:
    return _dto(ruta, equipo_repo.vigentes_de(db, ruta.id))


def _obtener(db: Session, ruta_id: uuid.UUID, *, bloquear: bool = False) -> Ruta:
    ruta = ruta_repo.obtener(db, ruta_id, bloquear=bloquear)
    if ruta is None:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta no existe.", status_code=404)
    return ruta


def _codigo_duplicado() -> AppError:
    return AppError("RUTA_DUPLICADA", "Ya existe una ruta con ese código.", status_code=409)


def _validar_vendedor(
    db: Session, vendedor_id: uuid.UUID | None, ruta_id: uuid.UUID | None
) -> None:
    """El usuario debe existir y no contradecir al empleado vendedor del equipo vigente."""
    if vendedor_id is None:
        return
    if not ruta_repo.usuario_existe(db, vendedor_id):
        raise AppError("USUARIO_NO_ENCONTRADO", "El vendedor indicado no existe.", status_code=404)
    if ruta_id is None:
        return
    for fila in equipo_repo.vigentes_de(db, ruta_id):
        if fila.rol_en_ruta == RolEnRuta.VENDEDOR:
            empleado = empleado_repo.obtener(db, fila.empleado_id)
            if empleado is not None:
                validar_vendedor_coherente(
                    vendedor_id, empleado.usuario_id, empleado.nombre_completo
                )


@auditar
def listar(db: Session, *, activa: bool | None) -> list[RutaAdminOut]:
    rutas = ruta_repo.listar(db, activa=activa)
    equipos = equipo_repo.vigentes_de_rutas(db, {r.id for r in rutas})
    return [_dto(r, equipos[r.id]) for r in rutas]


@auditar
def obtener(db: Session, ruta_id: uuid.UUID) -> RutaAdminOut:
    return _dto_de(db, _obtener(db, ruta_id))


@auditar
def crear(db: Session, datos: RutaCreate, actor_id: uuid.UUID) -> RutaAdminOut:
    codigo = datos.codigo.strip().upper()
    if not codigo:
        raise AppError("RUTA_CODIGO_INVALIDO", "El código de la ruta no puede estar vacío.")
    if ruta_repo.obtener_por_codigo(db, codigo) is not None:
        raise _codigo_duplicado()
    _validar_vendedor(db, datos.vendedor_id, None)
    try:
        ruta = ruta_repo.crear(
            db,
            {
                "codigo": codigo,
                "nombre": datos.nombre.strip(),
                "zona": (datos.zona or "").strip() or None,
                "vendedor_id": datos.vendedor_id,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _codigo_duplicado() from exc
    return _dto_de(db, ruta)


@auditar
def actualizar(
    db: Session, ruta_id: uuid.UUID, datos: RutaUpdate, actor_id: uuid.UUID
) -> RutaAdminOut:
    ruta = _obtener(db, ruta_id, bloquear=True)
    campos = datos.model_fields_set
    if datos.nombre is not None:
        ruta.nombre = datos.nombre.strip()
    if "zona" in campos:
        ruta.zona = (datos.zona or "").strip() or None
    if "vendedor_id" in campos:  # None explícito = quitar el vendedor
        _validar_vendedor(db, datos.vendedor_id, ruta.id)
        ruta.vendedor_id = datos.vendedor_id
    db.commit()
    return _dto_de(db, ruta)


@auditar
def desactivar(db: Session, ruta_id: uuid.UUID, actor_id: uuid.UUID) -> RutaAdminOut:
    """Baja lógica idempotente. Se bloquea con liquidaciones en borrador o cargas vigentes."""
    ruta = _obtener(db, ruta_id, bloquear=True)
    if ruta.activa:
        borradores = ruta_repo.liquidaciones_en_borrador(db, ruta.id)
        if borradores:
            raise AppError(
                "RUTA_CON_LIQUIDACIONES",
                "No se puede desactivar: la ruta tiene liquidaciones en borrador.",
                status_code=409,
                detalle={"liquidaciones": [str(x) for x in borradores]},
            )
        cargas = ruta_repo.cargas_vigentes(db, ruta.id)
        if cargas:
            raise AppError(
                "RUTA_CON_CARGAS_VIGENTES",
                "No se puede desactivar: la ruta tiene cargas vigentes.",
                status_code=409,
                detalle={"cargas": [str(x) for x in cargas]},
            )
        ruta.activa = False
        db.commit()
    return _dto_de(db, ruta)


@auditar
def activar(db: Session, ruta_id: uuid.UUID, actor_id: uuid.UUID) -> RutaAdminOut:
    ruta = _obtener(db, ruta_id, bloquear=True)
    if not ruta.activa:
        ruta.activa = True
        db.commit()
    return _dto_de(db, ruta)
