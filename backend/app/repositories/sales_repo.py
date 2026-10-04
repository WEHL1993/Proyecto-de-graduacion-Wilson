"""Consultas del agregado de ventas: lotes ETL, ventas históricas y comisiones."""

import uuid
from collections.abc import Collection, Iterator, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.enums import EstadoLoteEtl, OrigenDatos
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Producto
from app.domain.models.sales import Comision, EtlLote, VentaHistorica

_TAMANO_LOTE = 2000
_UQ_VENTA = "uq_ventas_historicas_fecha_producto_ruta_vendedor"
_UQ_COMISION = "uq_comisiones_venta_id_vendedor_id"


class VentaPersistida(NamedTuple):
    id: int
    vendedor_id: uuid.UUID | None
    fecha_venta: date
    monto_total: Decimal


def _en_bloques(filas: Sequence[dict[str, Any]]) -> Iterator[Sequence[dict[str, Any]]]:
    for i in range(0, len(filas), _TAMANO_LOTE):
        yield filas[i : i + _TAMANO_LOTE]


# ------------------------------------------------------------------ etl_lotes
def obtener_lote_por_checksum(db: Session, checksum: str) -> EtlLote | None:
    return db.execute(
        select(EtlLote).where(EtlLote.checksum_sha256 == checksum)
    ).scalar_one_or_none()


def crear_lote(
    db: Session, *, usuario_id: uuid.UUID, archivo_nombre: str, checksum: str
) -> EtlLote:
    """Inserta el lote en estado `recibido`. Lanza `IntegrityError` si el checksum ya existe."""
    lote = EtlLote(
        usuario_id=usuario_id,
        archivo_nombre=archivo_nombre,
        checksum_sha256=checksum,
        estado=EstadoLoteEtl.RECIBIDO,
    )
    db.add(lote)
    db.flush()
    return lote


def actualizar_lote(
    lote: EtlLote,
    *,
    estado: EstadoLoteEtl,
    filas_totales: int,
    filas_validas: int,
    filas_rechazadas: int,
    errores: list[dict[str, Any]] | None,
) -> None:
    lote.estado = estado
    lote.filas_totales = filas_totales
    lote.filas_validas = filas_validas
    lote.filas_rechazadas = filas_rechazadas
    lote.errores = errores


def listar_lotes(
    db: Session, *, estado: EstadoLoteEtl | None, limit: int, offset: int
) -> tuple[list[tuple[EtlLote, str]], int]:
    """Lotes ETL (Excel) más recientes primero, con el nombre de quien los cargó, y el total.

    Los lotes de liquidación (ADR-14) no son cargas de archivo y no aparecen aquí."""
    filtros = [EtlLote.origen == OrigenDatos.EXCEL_HISTORICO]
    if estado is not None:
        filtros.append(EtlLote.estado == estado)
    total = db.scalar(select(func.count()).select_from(EtlLote).where(*filtros)) or 0
    filas = db.execute(
        select(EtlLote, Usuario.nombre_completo)
        .join(Usuario, Usuario.id == EtlLote.usuario_id)
        .where(*filtros)
        .order_by(EtlLote.creado_en.desc(), EtlLote.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(lote, nombre) for lote, nombre in filas], total


# ------------------------------------------------------------------ lotes de liquidación
def crear_lote_liquidacion(
    db: Session, *, usuario_id: uuid.UUID, archivo_nombre: str, checksum: str, filas: int
) -> EtlLote:
    """Lote `cargado` de origen `liquidacion` (uno por liquidación cerrada, ADR-14)."""
    lote = EtlLote(
        usuario_id=usuario_id,
        archivo_nombre=archivo_nombre,
        checksum_sha256=checksum,
        estado=EstadoLoteEtl.CARGADO,
        origen=OrigenDatos.LIQUIDACION,
        filas_totales=filas,
        filas_validas=filas,
    )
    db.add(lote)
    db.flush()
    return lote


def actualizar_lote_liquidacion(
    db: Session, lote: EtlLote, *, usuario_id: uuid.UUID, checksum: str, filas: int
) -> None:
    lote.usuario_id = usuario_id
    lote.checksum_sha256 = checksum
    lote.estado = EstadoLoteEtl.CARGADO
    lote.filas_totales = filas
    lote.filas_validas = filas
    db.flush()


def sellar_lote_anulado(db: Session, lote: EtlLote, checksum: str) -> None:
    """Un lote anulado queda `rechazado` (sin ventas) y libera su checksum original."""
    lote.estado = EstadoLoteEtl.RECHAZADO
    lote.checksum_sha256 = checksum
    lote.filas_validas = 0
    lote.filas_rechazadas = 0
    db.flush()


def obtener_lote(db: Session, lote_id: uuid.UUID) -> EtlLote | None:
    return db.get(EtlLote, lote_id)


# ------------------------------------------------------------------ ventas_historicas
def eliminar_ventas_de_lote(
    db: Session, lote_id: uuid.UUID, *, conservar_productos: Collection[uuid.UUID] = ()
) -> int:
    """Borra las ventas del lote salvo las de `conservar_productos` (sus comisiones caen en
    cascada). Devuelve cuántas se borraron."""
    stmt = delete(VentaHistorica).where(VentaHistorica.lote_id == lote_id)
    if conservar_productos:
        stmt = stmt.where(VentaHistorica.producto_id.not_in(list(conservar_productos)))
    return db.execute(stmt).rowcount


def hay_ventas_excel(db: Session, fecha: date, ruta_id: uuid.UUID) -> bool:
    """¿La línea base Excel ya trae ventas de esa fecha/ruta? (no se pisa, ADR-14)."""
    stmt = (
        select(VentaHistorica.id)
        .join(EtlLote, EtlLote.id == VentaHistorica.lote_id)
        .where(
            VentaHistorica.fecha_venta == fecha,
            VentaHistorica.ruta_id == ruta_id,
            EtlLote.origen == OrigenDatos.EXCEL_HISTORICO,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def upsert_ventas(db: Session, filas: Sequence[dict[str, Any]]) -> list[VentaPersistida]:
    """Inserción idempotente por lotes: ante `(fecha, producto, ruta, vendedor)` repetido
    actualiza cantidad/precio/monto y reasigna el lote. `filas` no debe repetir la clave."""
    persistidas: list[VentaPersistida] = []
    for bloque in _en_bloques(filas):
        stmt = pg_insert(VentaHistorica).values(list(bloque))
        stmt = stmt.on_conflict_do_update(
            constraint=_UQ_VENTA,
            set_={
                "lote_id": stmt.excluded.lote_id,
                "cantidad": stmt.excluded.cantidad,
                "precio_unitario": stmt.excluded.precio_unitario,
                "monto_total": stmt.excluded.monto_total,
            },
        ).returning(
            VentaHistorica.id,
            VentaHistorica.vendedor_id,
            VentaHistorica.fecha_venta,
            VentaHistorica.monto_total,
        )
        persistidas.extend(VentaPersistida(*fila) for fila in db.execute(stmt))
    return persistidas


# ------------------------------------------------------------------ comisiones
def upsert_comisiones(db: Session, filas: Sequence[dict[str, Any]]) -> int:
    """Recalcula (no duplica) la comisión de cada `(venta, vendedor)`."""
    for bloque in _en_bloques(filas):
        stmt = pg_insert(Comision).values(list(bloque))
        stmt = stmt.on_conflict_do_update(
            constraint=_UQ_COMISION,
            set_={
                "periodo": stmt.excluded.periodo,
                "porcentaje": stmt.excluded.porcentaje,
                "monto": stmt.excluded.monto,
            },
        )
        db.execute(stmt)
    return len(filas)


# ------------------------------------------------------------------ catálogo por ruta
def productos_de_ruta(db: Session, ruta_id: uuid.UUID) -> list[uuid.UUID]:
    """Productos activos con ventas históricas en la ruta (los que puede cargar), por id."""
    stmt = (
        select(VentaHistorica.producto_id)
        .join(Producto, Producto.id == VentaHistorica.producto_id)
        .where(VentaHistorica.ruta_id == ruta_id, Producto.activo.is_(True))
        .distinct()
        .order_by(VentaHistorica.producto_id)
    )
    return list(db.scalars(stmt))


# ------------------------------------------------------------------ serie diaria para ML
def ventas_diarias(
    db: Session,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    producto_ids: Sequence[uuid.UUID] | None = None,
    ruta_id: uuid.UUID | None = None,
    origenes: Sequence[OrigenDatos] | None = None,
) -> list[tuple[date, uuid.UUID, uuid.UUID, Decimal]]:
    """`(fecha, producto_id, ruta_id, cantidad)` sumando vendedores, ordenado por fecha.

    `origenes` restringe a los lotes de esa procedencia (`None` = todas, ADR-14)."""
    stmt = select(
        VentaHistorica.fecha_venta,
        VentaHistorica.producto_id,
        VentaHistorica.ruta_id,
        func.sum(VentaHistorica.cantidad),
    )
    if origenes is not None:
        stmt = stmt.join(EtlLote, EtlLote.id == VentaHistorica.lote_id).where(
            EtlLote.origen.in_([o.value for o in origenes])
        )
    stmt = stmt.group_by(
        VentaHistorica.fecha_venta, VentaHistorica.producto_id, VentaHistorica.ruta_id
    )
    if desde is not None:
        stmt = stmt.where(VentaHistorica.fecha_venta >= desde)
    if hasta is not None:
        stmt = stmt.where(VentaHistorica.fecha_venta <= hasta)
    if producto_ids is not None:
        stmt = stmt.where(VentaHistorica.producto_id.in_(producto_ids))
    if ruta_id is not None:
        stmt = stmt.where(VentaHistorica.ruta_id == ruta_id)
    return [tuple(fila) for fila in db.execute(stmt.order_by(VentaHistorica.fecha_venta))]


def ultima_fecha_venta(db: Session) -> date | None:
    return db.scalar(select(func.max(VentaHistorica.fecha_venta)))


def ultima_fecha_venta_de_origen(db: Session, origen: OrigenDatos) -> date | None:
    stmt = (
        select(func.max(VentaHistorica.fecha_venta))
        .join(EtlLote, EtlLote.id == VentaHistorica.lote_id)
        .where(EtlLote.origen == origen)
    )
    return db.scalar(stmt)


def rangos_por_ruta_de_origen(
    db: Session, origen: OrigenDatos
) -> dict[uuid.UUID, tuple[date, date]]:
    """Rango `(primera, última)` fecha con ventas de cada ruta para un origen."""
    stmt = (
        select(
            VentaHistorica.ruta_id,
            func.min(VentaHistorica.fecha_venta),
            func.max(VentaHistorica.fecha_venta),
        )
        .join(EtlLote, EtlLote.id == VentaHistorica.lote_id)
        .where(EtlLote.origen == origen)
        .group_by(VentaHistorica.ruta_id)
    )
    return {ruta: (desde, hasta) for ruta, desde, hasta in db.execute(stmt)}


def resumen_por_origen(db: Session) -> dict[str, dict[str, Any]]:
    """Filas y rango de fechas de `ventas_historicas` por origen (trazabilidad del modelo)."""
    stmt = (
        select(
            EtlLote.origen,
            func.count(VentaHistorica.id),
            func.min(VentaHistorica.fecha_venta),
            func.max(VentaHistorica.fecha_venta),
        )
        .join(EtlLote, EtlLote.id == VentaHistorica.lote_id)
        .group_by(EtlLote.origen)
    )
    return {
        origen: {"filas": filas, "desde": desde, "hasta": hasta}
        for origen, filas, desde, hasta in db.execute(stmt)
    }
