"""Consultas agregadas de solo lectura para los reportes gerenciales."""

import uuid
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.domain.enums import EstadoCarga
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Inventario, Producto, Ruta
from app.domain.models.ml import PronosticoDemanda
from app.domain.models.operations import CargaRuta, DetalleCarga
from app.domain.models.sales import Comision, VentaHistorica

CERO = Decimal("0")


class VentaRuta(NamedTuple):
    ruta_id: uuid.UUID
    unidades: Decimal
    monto: Decimal
    costo: Decimal


class QuiebreRuta(NamedTuple):
    ruta_id: uuid.UUID
    cargas: int
    lineas: int
    ajustadas: int
    no_cubiertas: Decimal


class LiquidacionFila(NamedTuple):
    vendedor_id: uuid.UUID
    vendedor: str
    periodo: str
    ventas: int
    monto_vendido: Decimal
    comision: Decimal


def _filtro_ruta(stmt: Select, columna, ruta_id: uuid.UUID | None) -> Select:
    return stmt if ruta_id is None else stmt.where(columna == ruta_id)


def rutas(db: Session, ruta_id: uuid.UUID | None = None) -> dict[uuid.UUID, Ruta]:
    stmt = _filtro_ruta(select(Ruta).order_by(Ruta.codigo), Ruta.id, ruta_id)
    return {r.id: r for r in db.scalars(stmt)}


def rango_por_defecto(db: Session, *, con_proyeccion: bool = False) -> date | None:
    """Última fecha con actividad comercial: venta real y, opcionalmente, proyección (que
    suele ser futura y dejaría fuera las ventas reales en reportes que no la usan)."""
    fechas = [db.scalar(select(func.max(VentaHistorica.fecha_venta)))]
    if con_proyeccion:
        fechas.append(db.scalar(select(func.max(PronosticoDemanda.fecha_objetivo))))
    fechas = [f for f in fechas if f is not None]
    return max(fechas) if fechas else None


def valor_inventario(db: Session) -> Decimal:
    """Σ stock_actual × costo_unitario de todo el inventario."""
    stmt = select(
        func.coalesce(func.sum(Inventario.stock_actual * Producto.costo_unitario), 0)
    ).join(Producto, Producto.id == Inventario.producto_id)
    return db.scalar(stmt) or CERO


def ventas_por_ruta(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> list[VentaRuta]:
    stmt = (
        select(
            VentaHistorica.ruta_id,
            func.sum(VentaHistorica.cantidad),
            func.sum(VentaHistorica.monto_total),
            func.sum(VentaHistorica.cantidad * Producto.costo_unitario),
        )
        .join(Producto, Producto.id == VentaHistorica.producto_id)
        .where(VentaHistorica.fecha_venta.between(desde, hasta))
        .group_by(VentaHistorica.ruta_id)
    )
    stmt = _filtro_ruta(stmt, VentaHistorica.ruta_id, ruta_id)
    return [VentaRuta(*fila) for fila in db.execute(stmt)]


def quiebres_por_ruta(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> list[QuiebreRuta]:
    """Líneas de carga (no rechazadas) limitadas por stock y demanda que no se pudo cubrir."""
    ajustada = func.sum(case((DetalleCarga.ajustado_por_stock.is_(True), 1), else_=0))
    stmt = (
        select(
            CargaRuta.ruta_id,
            func.count(func.distinct(CargaRuta.id)),
            func.count(DetalleCarga.id),
            ajustada,
            func.sum(DetalleCarga.cantidad_predicha - DetalleCarga.cantidad_sugerida),
        )
        .join(DetalleCarga, DetalleCarga.carga_id == CargaRuta.id)
        .where(
            CargaRuta.fecha_operacion.between(desde, hasta),
            CargaRuta.estado != EstadoCarga.RECHAZADA,
        )
        .group_by(CargaRuta.ruta_id)
    )
    stmt = _filtro_ruta(stmt, CargaRuta.ruta_id, ruta_id)
    return [QuiebreRuta(r, c, n_l, int(a or 0), n or CERO) for r, c, n_l, a, n in db.execute(stmt)]


def liquidacion_comisiones(
    db: Session,
    periodo_desde: str,
    periodo_hasta: str,
    vendedor_id: uuid.UUID | None,
    ruta_id: uuid.UUID | None,
) -> list[LiquidacionFila]:
    """Comisiones (`comisiones`) sobre las ventas que las originan (`ventas_historicas`)."""
    stmt = (
        select(
            Comision.vendedor_id,
            Usuario.nombre_completo,
            Comision.periodo,
            func.count(Comision.id),
            func.sum(VentaHistorica.monto_total),
            func.sum(Comision.monto),
        )
        .join(VentaHistorica, VentaHistorica.id == Comision.venta_id)
        .join(Usuario, Usuario.id == Comision.vendedor_id)
        .where(Comision.periodo.between(periodo_desde, periodo_hasta))
        .group_by(Comision.vendedor_id, Usuario.nombre_completo, Comision.periodo)
        .order_by(Comision.periodo, Usuario.nombre_completo)
    )
    if vendedor_id is not None:
        stmt = stmt.where(Comision.vendedor_id == vendedor_id)
    stmt = _filtro_ruta(stmt, VentaHistorica.ruta_id, ruta_id)
    return [LiquidacionFila(*fila) for fila in db.execute(stmt)]


def _proyeccion_vigente(desde: date, hasta: date, ruta_id: uuid.UUID | None):
    """Una fila por (producto, ruta, fecha): la proyección más reciente (evita duplicar
    horizontes/modelos que pronostican el mismo día)."""
    stmt = (
        select(
            PronosticoDemanda.ruta_id,
            PronosticoDemanda.fecha_objetivo,
            PronosticoDemanda.demanda_predicha,
        )
        .where(
            PronosticoDemanda.ruta_id.is_not(None),
            PronosticoDemanda.fecha_objetivo.between(desde, hasta),
        )
        .distinct(
            PronosticoDemanda.producto_id,
            PronosticoDemanda.ruta_id,
            PronosticoDemanda.fecha_objetivo,
        )
        .order_by(
            PronosticoDemanda.producto_id,
            PronosticoDemanda.ruta_id,
            PronosticoDemanda.fecha_objetivo,
            PronosticoDemanda.generado_en.desc(),
            PronosticoDemanda.id.desc(),
        )
    )
    return _filtro_ruta(stmt, PronosticoDemanda.ruta_id, ruta_id).subquery()


def proyectado_por_ruta(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> dict[uuid.UUID, Decimal]:
    p = _proyeccion_vigente(desde, hasta, ruta_id)
    stmt = select(p.c.ruta_id, func.sum(p.c.demanda_predicha)).group_by(p.c.ruta_id)
    return {r: total for r, total in db.execute(stmt)}


def proyectado_por_dia(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> dict[date, Decimal]:
    p = _proyeccion_vigente(desde, hasta, ruta_id)
    stmt = select(p.c.fecha_objetivo, func.sum(p.c.demanda_predicha)).group_by(p.c.fecha_objetivo)
    return {f: total for f, total in db.execute(stmt)}


def real_por_ruta(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> dict[uuid.UUID, Decimal]:
    stmt = (
        select(VentaHistorica.ruta_id, func.sum(VentaHistorica.cantidad))
        .where(VentaHistorica.fecha_venta.between(desde, hasta))
        .group_by(VentaHistorica.ruta_id)
    )
    return {
        r: total for r, total in db.execute(_filtro_ruta(stmt, VentaHistorica.ruta_id, ruta_id))
    }


def real_por_dia(
    db: Session, desde: date, hasta: date, ruta_id: uuid.UUID | None
) -> dict[date, Decimal]:
    stmt = (
        select(VentaHistorica.fecha_venta, func.sum(VentaHistorica.cantidad))
        .where(VentaHistorica.fecha_venta.between(desde, hasta))
        .group_by(VentaHistorica.fecha_venta)
    )
    return {
        f: total for f, total in db.execute(_filtro_ruta(stmt, VentaHistorica.ruta_id, ruta_id))
    }
