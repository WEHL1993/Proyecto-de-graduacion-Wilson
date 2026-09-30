"""Histórico comercial cargado por ETL: lotes, ventas históricas y comisiones."""

import uuid
from datetime import date

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import EstadoLoteEtl, sql_in
from app.domain.models.base import (
    Base,
    Cantidad,
    CreadoEnMixin,
    Monto,
    PorcentajeError,
    UUIDPkMixin,
)


class EtlLote(UUIDPkMixin, CreadoEnMixin, Base):
    __tablename__ = "etl_lotes"
    __table_args__ = (
        CheckConstraint(sql_in("estado", EstadoLoteEtl), name="estado_valido"),
        CheckConstraint(
            "filas_totales >= 0 AND filas_validas >= 0 AND filas_rechazadas >= 0 "
            "AND filas_validas + filas_rechazadas <= filas_totales",
            name="conteos_coherentes",
        ),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    archivo_nombre: Mapped[str] = mapped_column(String(255))
    # Bloquea la carga duplicada del mismo archivo (TC-ETL-02).
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64), unique=True)
    estado: Mapped[str] = mapped_column(
        String(12), server_default=text(f"'{EstadoLoteEtl.RECIBIDO}'")
    )
    filas_totales: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    filas_validas: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    filas_rechazadas: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    errores: Mapped[list | dict | None] = mapped_column(JSONB)


class VentaHistorica(Base):
    __tablename__ = "ventas_historicas"
    __table_args__ = (
        # Idempotencia de re-cargas (ON CONFLICT en ETL). NULLS NOT DISTINCT (PG15+) para
        # que una venta sin vendedor no se duplique al recargar.
        UniqueConstraint(
            "fecha_venta",
            "producto_id",
            "ruta_id",
            "vendedor_id",
            name="uq_ventas_historicas_fecha_producto_ruta_vendedor",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("cantidad >= 0 AND precio_unitario >= 0", name="calidad_datos"),
        CheckConstraint("monto_total >= 0", name="monto_no_negativo"),
        Index("ix_ventas_historicas_producto_fecha", "producto_id", "fecha_venta"),
        Index("ix_ventas_historicas_ruta_fecha", "ruta_id", "fecha_venta"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    lote_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("etl_lotes.id", ondelete="RESTRICT"), index=True
    )
    fecha_venta: Mapped[date] = mapped_column(Date)
    producto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("productos.id", ondelete="RESTRICT"))
    ruta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rutas.id", ondelete="RESTRICT"))
    vendedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    cantidad: Mapped[Cantidad]
    precio_unitario: Mapped[Monto]
    monto_total: Mapped[Monto]


class Comision(UUIDPkMixin, Base):
    __tablename__ = "comisiones"
    __table_args__ = (
        UniqueConstraint("venta_id", "vendedor_id"),
        CheckConstraint(r"periodo ~ '^\d{4}-(0[1-9]|1[0-2])$'", name="periodo_formato"),
        CheckConstraint("porcentaje >= 0 AND porcentaje <= 100", name="porcentaje_rango"),
        CheckConstraint("monto >= 0", name="monto_no_negativo"),
        Index("ix_comisiones_vendedor_periodo", "vendedor_id", "periodo"),
    )

    vendedor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    venta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ventas_historicas.id", ondelete="CASCADE")
    )
    periodo: Mapped[str] = mapped_column(CHAR(7))  # YYYY-MM
    porcentaje: Mapped[PorcentajeError]
    monto: Mapped[Monto]
