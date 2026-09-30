"""Consultas del agregado de ventas: lotes ETL, ventas históricas y comisiones."""

import uuid
from collections.abc import Iterator, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.enums import EstadoLoteEtl
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


# ------------------------------------------------------------------ ventas_historicas
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
