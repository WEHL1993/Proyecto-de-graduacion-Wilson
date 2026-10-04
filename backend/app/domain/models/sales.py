"""Histórico comercial: lotes (ETL o liquidación), ventas históricas, comisiones y liquidaciones."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import EstadoLiquidacion, EstadoLoteEtl, OrigenDatos, sql_in
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
        CheckConstraint(sql_in("origen", OrigenDatos), name="origen_valido"),
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
    # ADR-14: los lotes previos a la liquidación diaria son la línea base `excel_historico`.
    origen: Mapped[str] = mapped_column(
        String(20), server_default=text(f"'{OrigenDatos.EXCEL_HISTORICO}'")
    )


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


class LiquidacionDiaria(UUIDPkMixin, Base):
    """Cabecera de la liquidación del día por ruta y vendedor (ADR-14): dinero y cuadre de caja."""

    __tablename__ = "liquidaciones_diarias"
    __table_args__ = (
        CheckConstraint(sql_in("estado", EstadoLiquidacion), name="estado_valido"),
        CheckConstraint("version >= 1", name="version_positiva"),
        CheckConstraint(
            "venta_total >= 0 AND total_efectivo >= 0 AND total_transferencia >= 0 "
            "AND total_credito >= 0 AND cobro_saldos_anteriores >= 0 AND gastos_ruta >= 0 "
            "AND efectivo_entregado >= 0",
            name="montos_no_negativos",
        ),
        # Una liquidación cerrada siempre cuadra el desglose del pago con la venta (un borrador
        # puede guardarse incompleto).
        CheckConstraint(
            "estado <> 'cerrada' "
            "OR venta_total = total_efectivo + total_transferencia + total_credito",
            name="venta_igual_pagos",
        ),
        CheckConstraint(
            "efectivo_esperado = total_efectivo + cobro_saldos_anteriores - gastos_ruta "
            "AND diferencia_caja = efectivo_entregado - efectivo_esperado",
            name="cuadre_caja_coherente",
        ),
        CheckConstraint(
            "estado <> 'cerrada' OR (cerrado_en IS NOT NULL AND lote_id IS NOT NULL)",
            name="cierre_completo",
        ),
        CheckConstraint(
            "estado <> 'anulada' OR (anulado_en IS NOT NULL AND anulado_motivo IS NOT NULL)",
            name="anulacion_completa",
        ),
        # Una sola liquidación vigente por fecha/ruta/vendedor.
        Index(
            "uq_liquidaciones_diarias_vigente",
            "fecha",
            "ruta_id",
            "vendedor_id",
            unique=True,
            postgresql_where=text("estado <> 'anulada'"),
        ),
        Index("ix_liquidaciones_diarias_fecha_ruta", "fecha", "ruta_id"),
    )

    fecha: Mapped[date] = mapped_column(Date)
    ruta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rutas.id", ondelete="RESTRICT"))
    vendedor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    estado: Mapped[str] = mapped_column(
        String(10), server_default=text(f"'{EstadoLiquidacion.BORRADOR}'")
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    lote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("etl_lotes.id", ondelete="RESTRICT"), index=True
    )
    venta_total: Mapped[Monto] = mapped_column(server_default=text("0"))
    total_efectivo: Mapped[Monto] = mapped_column(server_default=text("0"))
    total_transferencia: Mapped[Monto] = mapped_column(server_default=text("0"))
    total_credito: Mapped[Monto] = mapped_column(server_default=text("0"))
    cobro_saldos_anteriores: Mapped[Monto] = mapped_column(server_default=text("0"))
    gastos_ruta: Mapped[Monto] = mapped_column(server_default=text("0"))
    efectivo_esperado: Mapped[Monto] = mapped_column(server_default=text("0"))
    efectivo_entregado: Mapped[Monto] = mapped_column(server_default=text("0"))
    diferencia_caja: Mapped[Monto] = mapped_column(server_default=text("0"))
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    cerrado_en: Mapped[datetime | None]
    anulado_en: Mapped[datetime | None]
    anulado_motivo: Mapped[str | None] = mapped_column(Text)
    # Bitácora de creación/cierre/corrección/anulación (usuario, antes y después).
    historial: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))

    detalles: Mapped[list["LiquidacionDetalle"]] = relationship(
        back_populates="liquidacion",
        cascade="all, delete-orphan",
        order_by="LiquidacionDetalle.producto_id",
    )


class LiquidacionDetalle(UUIDPkMixin, Base):
    """Línea por presentación: unidades cargadas/vendidas/devueltas/merma y precio."""

    __tablename__ = "liquidacion_detalles"
    __table_args__ = (
        UniqueConstraint("liquidacion_id", "producto_id"),
        CheckConstraint(
            "cantidad_cargada >= 0 AND cantidad_vendida >= 0 AND cantidad_devuelta >= 0 "
            "AND cantidad_merma >= 0 AND precio_unitario >= 0 AND monto_total >= 0",
            name="valores_no_negativos",
        ),
        CheckConstraint(
            "cantidad_vendida + cantidad_devuelta + cantidad_merma <= cantidad_cargada",
            name="unidades_no_exceden_cargada",
        ),
        CheckConstraint(
            "monto_total = round(cantidad_vendida * precio_unitario, 2)",
            name="monto_coherente",
        ),
    )

    liquidacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("liquidaciones_diarias.id", ondelete="CASCADE")
    )
    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    cantidad_cargada: Mapped[Cantidad]
    cantidad_vendida: Mapped[Cantidad]
    cantidad_devuelta: Mapped[Cantidad] = mapped_column(server_default=text("0"))
    cantidad_merma: Mapped[Cantidad] = mapped_column(server_default=text("0"))
    precio_unitario: Mapped[Monto]
    monto_total: Mapped[Monto]
    # Se agotó antes de terminar la ruta: la venta es un piso de la demanda (censura).
    agotado: Mapped[bool] = mapped_column(Boolean, server_default=false())
    justificacion_carga: Mapped[str | None] = mapped_column(Text)

    liquidacion: Mapped[LiquidacionDiaria] = relationship(back_populates="detalles")
