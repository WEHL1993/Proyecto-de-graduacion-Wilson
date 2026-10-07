"""Persistencia de `equipo_ruta`: integrantes de cada ruta con porcentaje y vigencia (M02)."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import RolEnRuta
from app.domain.models.catalog import Empleado, EquipoRuta, Ruta


def vigentes_de(db: Session, ruta_id: uuid.UUID) -> Sequence[EquipoRuta]:
    stmt = (
        select(EquipoRuta)
        .where(EquipoRuta.ruta_id == ruta_id, EquipoRuta.vigente_hasta.is_(None))
        .order_by(EquipoRuta.rol_en_ruta.desc(), EquipoRuta.creado_en)
    )
    return db.scalars(stmt).all()


def historial_de(db: Session, ruta_id: uuid.UUID) -> Sequence[EquipoRuta]:
    """Integrantes con la vigencia ya cerrada, del más reciente al más antiguo."""
    stmt = (
        select(EquipoRuta)
        .where(EquipoRuta.ruta_id == ruta_id, EquipoRuta.vigente_hasta.is_not(None))
        .order_by(EquipoRuta.vigente_hasta.desc(), EquipoRuta.creado_en)
    )
    return db.scalars(stmt).all()


def vigentes_de_rutas(db: Session, ruta_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[EquipoRuta]]:
    agrupados: dict[uuid.UUID, list[EquipoRuta]] = {rid: [] for rid in ruta_ids}
    if not ruta_ids:
        return agrupados
    stmt = select(EquipoRuta).where(
        EquipoRuta.ruta_id.in_(ruta_ids), EquipoRuta.vigente_hasta.is_(None)
    )
    for fila in db.scalars(stmt):
        agrupados[fila.ruta_id].append(fila)
    return agrupados


def cerrar(db: Session, filas: Sequence[EquipoRuta], hasta_por_defecto: date) -> None:
    """Cierra las vigencias (nunca las borra). `vigente_hasta` no puede ser anterior al inicio."""
    for fila in filas:
        fila.vigente_hasta = max(hasta_por_defecto, fila.vigente_desde)
    db.flush()


def agregar(
    db: Session,
    *,
    ruta_id: uuid.UUID,
    empleado_id: uuid.UUID,
    rol_en_ruta: str,
    porcentaje_reparto,
    vigente_desde: date,
) -> EquipoRuta:
    fila = EquipoRuta(
        ruta_id=ruta_id,
        empleado_id=empleado_id,
        rol_en_ruta=rol_en_ruta,
        porcentaje_reparto=porcentaje_reparto,
        vigente_desde=vigente_desde,
    )
    db.add(fila)
    db.flush()
    return fila


def vendedores_vigentes(db: Session) -> Sequence[tuple[Ruta, Empleado]]:
    """`(ruta activa, empleado vendedor vigente)`.

    Alimenta el informe de rutas desalineadas (`rutas.vendedor_id` ≠ `empleados.usuario_id`).
    """
    stmt = (
        select(Ruta, Empleado)
        .join(EquipoRuta, EquipoRuta.ruta_id == Ruta.id)
        .join(Empleado, Empleado.id == EquipoRuta.empleado_id)
        .where(
            EquipoRuta.vigente_hasta.is_(None),
            EquipoRuta.rol_en_ruta == RolEnRuta.VENDEDOR,
            Ruta.activa.is_(True),
        )
        .order_by(Ruta.codigo)
    )
    return [(r, e) for r, e in db.execute(stmt)]
