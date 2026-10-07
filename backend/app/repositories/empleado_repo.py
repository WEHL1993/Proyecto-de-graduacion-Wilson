"""Persistencia del agregado `Empleado` (personal de ruta, M02)."""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models.catalog import Empleado, EquipoRuta


def obtener(db: Session, empleado_id: uuid.UUID, *, bloquear: bool = False) -> Empleado | None:
    stmt = select(Empleado).where(Empleado.id == empleado_id)
    if bloquear:
        stmt = stmt.with_for_update()
    return db.scalars(stmt).one_or_none()


def obtener_varios(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Empleado]:
    ids = set(ids)
    if not ids:
        return {}
    return {e.id: e for e in db.scalars(select(Empleado).where(Empleado.id.in_(ids)))}


def por_usuario(db: Session, usuario_id: uuid.UUID) -> Empleado | None:
    return db.scalars(select(Empleado).where(Empleado.usuario_id == usuario_id)).first()


def listar(
    db: Session, *, activo: bool | None, q: str | None, limit: int, offset: int
) -> tuple[Sequence[Empleado], int]:
    filtros = []
    if activo is not None:
        filtros.append(Empleado.activo.is_(activo))
    if q:
        filtros.append(Empleado.nombre_completo.ilike(f"%{q.strip()}%"))
    base = select(Empleado).where(*filtros)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    filas = db.scalars(base.order_by(Empleado.nombre_completo).limit(limit).offset(offset)).all()
    return filas, total


def crear(db: Session, campos: dict[str, Any]) -> Empleado:
    empleado = Empleado(**campos)
    db.add(empleado)
    db.flush()
    return empleado


def rutas_vigentes_de(db: Session, empleado_id: uuid.UUID) -> Sequence[uuid.UUID]:
    """Rutas en las que el empleado integra el equipo vigente."""
    stmt = select(EquipoRuta.ruta_id).where(
        EquipoRuta.empleado_id == empleado_id, EquipoRuta.vigente_hasta.is_(None)
    )
    return db.scalars(stmt).all()
