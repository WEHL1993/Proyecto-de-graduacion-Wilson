"""Catálogos y existencias: categorías, proveedores, productos, rutas, inventario y kardex."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ReferenciaTipo, RolEnRuta, TipoMovimiento, sql_in
from app.domain.models.base import (
    AuditoriaMixin,
    Base,
    Cantidad,
    CreadoEnMixin,
    Monto,
    UUIDPkMixin,
)


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
        CheckConstraint("unidades_por_paquete > 0", name="unidades_por_paquete_positivas"),
        CheckConstraint("medida_ml IS NULL OR medida_ml > 0", name="medida_ml_positiva"),
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
    # M02 (ADR-18): la unidad de venta es el paquete; todo es compatible hacia atrás.
    unidades_por_paquete: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    medida_ml: Mapped[int | None] = mapped_column(Integer)
    sabor: Mapped[str | None] = mapped_column(String(60))


class ProductoAliasExcel(UUIDPkMixin, CreadoEnMixin, Base):
    """Nombre con el que un producto aparece en los Excel comerciales (`<medida>-<SABOR>`).

    Preparado para que el ETL empareje por alias sin depender de `productos.sku` (ADR-18).
    """

    __tablename__ = "producto_alias_excel"

    producto_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    alias: Mapped[str] = mapped_column(String(80), unique=True)


class Ruta(UUIDPkMixin, Base):
    __tablename__ = "rutas"

    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    zona: Mapped[str | None] = mapped_column(String(100))
    vendedor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    activa: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Empleado(UUIDPkMixin, AuditoriaMixin, Base):
    """Personal de ruta (vendedor, chofer, auxiliar). No es lo mismo que un usuario del sistema."""

    __tablename__ = "empleados"

    nombre_completo: Mapped[str] = mapped_column(String(150))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), unique=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true())


class EquipoRuta(UUIDPkMixin, CreadoEnMixin, Base):
    """Integrante de una ruta con su porcentaje de reparto y vigencia (cerrada, nunca borrada)."""

    __tablename__ = "equipo_ruta"
    __table_args__ = (
        CheckConstraint(sql_in("rol_en_ruta", RolEnRuta), name="rol_en_ruta_valido"),
        CheckConstraint("porcentaje_reparto BETWEEN 0 AND 100", name="porcentaje_en_rango"),
        CheckConstraint(
            "vigente_hasta IS NULL OR vigente_desde <= vigente_hasta", name="vigencia_coherente"
        ),
        Index(
            "uq_equipo_ruta_empleado_vigente",
            "ruta_id",
            "empleado_id",
            unique=True,
            postgresql_where=text("vigente_hasta IS NULL"),
        ),
        Index(
            "uq_equipo_ruta_vendedor_vigente",
            "ruta_id",
            unique=True,
            postgresql_where=text("rol_en_ruta = 'vendedor' AND vigente_hasta IS NULL"),
        ),
    )

    ruta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rutas.id", ondelete="RESTRICT"), index=True
    )
    empleado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empleados.id", ondelete="RESTRICT"), index=True
    )
    rol_en_ruta: Mapped[str] = mapped_column(String(10))
    porcentaje_reparto: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)


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
    # Justificación obligatoria de los ajustes manuales (ADR-16); NULL en el resto de movimientos.
    motivo: Mapped[str | None] = mapped_column(String(300))
