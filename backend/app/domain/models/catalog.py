"""Catálogos y existencias: categorías, proveedores, productos, rutas, inventario y kardex."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ReferenciaTipo, TipoMovimiento, sql_in
from app.domain.models.base import Base, Cantidad, CreadoEnMixin, Monto, UUIDPkMixin


class Categoria(UUIDPkMixin, Base):
    __tablename__ = "categorias"
    __table_args__ = (CheckConstraint("categoria_padre_id <> id", name="no_autorreferencia"),)

    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    categoria_padre_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="RESTRICT"), index=True
    )


class Proveedor(UUIDPkMixin, Base):
    __tablename__ = "proveedores"
    __table_args__ = (CheckConstraint("lead_time_dias >= 0", name="lead_time_no_negativo"),)

    nombre: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    lead_time_dias: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Producto(UUIDPkMixin, CreadoEnMixin, Base):
    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint(
            "precio_venta >= 0 AND costo_unitario >= 0 AND stock_minimo >= 0",
            name="valores_no_negativos",
        ),
    )

    sku: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    categoria_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categorias.id", ondelete="RESTRICT"), index=True
    )
    # Desviación documentada: nullable porque los Excel históricos no traen proveedor.
    proveedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proveedores.id", ondelete="RESTRICT"), index=True
    )
    unidad_medida: Mapped[str] = mapped_column(String(20), server_default=text("'unidad'"))
    precio_venta: Mapped[Monto] = mapped_column(server_default=text("0"))
    costo_unitario: Mapped[Monto] = mapped_column(server_default=text("0"))
    stock_minimo: Mapped[Cantidad] = mapped_column(server_default=text("0"))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Ruta(UUIDPkMixin, Base):
    __tablename__ = "rutas"

    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    zona: Mapped[str | None] = mapped_column(String(100))
    vendedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    activa: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Inventario(UUIDPkMixin, Base):
    __tablename__ = "inventario"
    __table_args__ = (
        CheckConstraint(
            "stock_actual >= 0 AND stock_reservado <= stock_actual", name="integridad_existencias"
        ),
        CheckConstraint("stock_reservado >= 0", name="reservado_no_negativo"),
    )

    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), unique=True
    )
    stock_actual: Mapped[Cantidad] = mapped_column(server_default=text("0"))
    stock_reservado: Mapped[Cantidad] = mapped_column(server_default=text("0"))
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    @property
    def stock_disponible(self) -> Decimal:
        return self.stock_actual - self.stock_reservado


class Kardex(Base):
    __tablename__ = "kardex"
    __table_args__ = (
        CheckConstraint(sql_in("tipo_movimiento", TipoMovimiento), name="tipo_movimiento_valido"),
        CheckConstraint(
            f"referencia_tipo IS NULL OR {sql_in('referencia_tipo', ReferenciaTipo)}",
            name="referencia_tipo_valida",
        ),
        CheckConstraint("saldo_resultante >= 0", name="saldo_no_negativo"),
        Index("ix_kardex_producto_fecha", "producto_id", text("fecha_movimiento DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    producto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("productos.id", ondelete="RESTRICT"))
    tipo_movimiento: Mapped[str] = mapped_column(String(12))
    cantidad: Mapped[Cantidad]
    saldo_resultante: Mapped[Cantidad]
    referencia_tipo: Mapped[str | None] = mapped_column(String(15))
    referencia_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # NULL cuando el movimiento lo genera un proceso (ETL / Worker).
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    fecha_movimiento: Mapped[datetime] = mapped_column(server_default=func.now())
