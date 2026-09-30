"""Operación comercial: cargas de ruta y pedidos a proveedor."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ESTADOS_CARGA_VIGENTE, EstadoCarga, EstadoPedido, sql_in
from app.domain.models.base import AuditoriaMixin, Base, Cantidad, Monto, UUIDPkMixin


class CargaRuta(UUIDPkMixin, Base):
    __tablename__ = "cargas_ruta"
    __table_args__ = (
        CheckConstraint(sql_in("estado", EstadoCarga), name="estado_valido"),
        # Una carga aprobada/despachada siempre registra quién y cuándo la aprobó (ADR-06).
        CheckConstraint(
            "estado NOT IN ('aprobada', 'despachada') "
            "OR (aprobado_por IS NOT NULL AND aprobada_en IS NOT NULL)",
            name="aprobacion_completa",
        ),
        # Una sola carga vigente por ruta y día (TC-LOAD-04).
        Index(
            "uq_cargas_ruta_vigente_ruta_fecha",
            "ruta_id",
            "fecha_operacion",
            unique=True,
            postgresql_where=text(sql_in("estado", ESTADOS_CARGA_VIGENTE)),
        ),
    )

    ruta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rutas.id", ondelete="RESTRICT"))
    fecha_operacion: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(
        String(25), server_default=text(f"'{EstadoCarga.BORRADOR}'")
    )
    modelo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modelos_ml.id", ondelete="RESTRICT"), index=True
    )
    generado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    aprobado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    observaciones: Mapped[str | None] = mapped_column(Text)
    generada_en: Mapped[datetime] = mapped_column(server_default=func.now())
    aprobada_en: Mapped[datetime | None]
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    detalles: Mapped[list["DetalleCarga"]] = relationship(
        back_populates="carga", cascade="all, delete-orphan"
    )


class DetalleCarga(UUIDPkMixin, Base):
    __tablename__ = "detalle_cargas"
    __table_args__ = (
        UniqueConstraint("carga_id", "producto_id"),
        CheckConstraint(
            "cantidad_predicha >= 0 AND stock_disponible_al_generar >= 0 "
            "AND cantidad_sugerida >= 0",
            name="cantidades_no_negativas",
        ),
        # Regla de negocio central: cantidad_sugerida = min(demanda_predicha, stock_disponible).
        CheckConstraint(
            "cantidad_sugerida = LEAST(cantidad_predicha, stock_disponible_al_generar)",
            name="sugerida_min_demanda_stock",
        ),
        # ADR-07: lo aprobado nunca excede el stock disponible al generar (TC-LOAD-02).
        CheckConstraint(
            "cantidad_aprobada IS NULL "
            "OR (cantidad_aprobada >= 0 AND cantidad_aprobada <= stock_disponible_al_generar)",
            name="aprobada_no_excede_stock",
        ),
    )

    carga_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cargas_ruta.id", ondelete="CASCADE"))
    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    cantidad_predicha: Mapped[Cantidad]
    stock_disponible_al_generar: Mapped[Cantidad]
    cantidad_sugerida: Mapped[Cantidad]
    cantidad_aprobada: Mapped[Cantidad | None]
    ajustado_por_stock: Mapped[bool] = mapped_column(Boolean, server_default=false())

    carga: Mapped[CargaRuta] = relationship(back_populates="detalles")


class PedidoProveedor(UUIDPkMixin, AuditoriaMixin, Base):
    __tablename__ = "pedidos_proveedor"
    __table_args__ = (
        CheckConstraint(sql_in("estado", EstadoPedido), name="estado_valido"),
        CheckConstraint("total >= 0", name="total_no_negativo"),
        CheckConstraint(
            "fecha_esperada IS NULL OR fecha_esperada >= fecha_pedido", name="fechas_coherentes"
        ),
        # Consultas filtradas por proveedor (aislamiento del actor Proveedor).
        Index("ix_pedidos_proveedor_proveedor_estado", "proveedor_id", "estado"),
    )

    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proveedores.id", ondelete="RESTRICT")
    )
    creado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    estado: Mapped[str] = mapped_column(
        String(12), server_default=text(f"'{EstadoPedido.BORRADOR}'")
    )
    fecha_pedido: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    fecha_esperada: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Monto] = mapped_column(server_default=text("0"))

    detalles: Mapped[list["DetallePedido"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )


class DetallePedido(UUIDPkMixin, Base):
    __tablename__ = "detalle_pedidos"
    __table_args__ = (
        UniqueConstraint("pedido_id", "producto_id"),
        CheckConstraint("cantidad > 0 AND costo_unitario >= 0", name="valores_validos"),
    )

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pedidos_proveedor.id", ondelete="CASCADE")
    )
    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    alerta_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alertas.id", ondelete="SET NULL"), index=True
    )
    cantidad: Mapped[Cantidad]
    costo_unitario: Mapped[Monto]

    pedido: Mapped[PedidoProveedor] = relationship(back_populates="detalles")
