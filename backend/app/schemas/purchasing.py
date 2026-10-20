"""DTOs del módulo de abastecimiento (`/purchasing`)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import EstadoPedido


class SugerenciaCompra(BaseModel):
    producto_id: UUID
    sku: str
    nombre: str
    proveedor_id: UUID
    proveedor_nombre: str
    lead_time_dias: int
    stock_actual: Decimal
    stock_minimo: Decimal
    demanda_proyectada: Decimal = Field(description="Demanda agregada de los próximos N días")
    cantidad_sugerida: Decimal = Field(
        description="max(0, (demanda_proyectada + stock_minimo) - stock_actual)"
    )
    costo_unitario: Decimal
    pronostico_disponible: bool = Field(
        description="False si no hubo pronóstico para el producto (demanda tomada como 0)"
    )


class SugerenciasResponse(BaseModel):
    horizonte_dias: int
    generado_en: datetime
    sugerencias: list[SugerenciaCompra]
    advertencias: list[str] = []


class PedidoItemIn(BaseModel):
    producto_id: UUID
    cantidad: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    costo_unitario: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
        description="Por defecto el del catálogo",
    )
    alerta_origen_id: UUID | None = None


class PedidoCreate(BaseModel):
    proveedor_id: UUID
    items: list[PedidoItemIn] = Field(min_length=1, max_length=200)
    fecha_esperada: date | None = None
    enviar: bool = Field(default=False, description="Aprobar y enviar de inmediato al proveedor")

    @model_validator(mode="after")
    def _sin_repetidos(self) -> Self:
        if len({i.producto_id for i in self.items}) != len(self.items):
            raise ValueError("`items` no puede repetir productos.")
        return self


class PedidoConfirmacion(BaseModel):
    fecha_esperada: date = Field(description="Fecha estimada de entrega informada por el proveedor")


class PedidoItemOut(BaseModel):
    producto_id: UUID
    sku: str
    producto_nombre: str
    cantidad: Decimal
    costo_unitario: Decimal
    subtotal: Decimal


class PedidoOut(BaseModel):
    id: UUID
    proveedor_id: UUID
    proveedor_nombre: str
    estado: EstadoPedido
    fecha_pedido: date
    fecha_esperada: date | None = None
    total: Decimal
    creado_por: UUID
    items: list[PedidoItemOut]


class PedidoPage(BaseModel):
    items: list[PedidoOut]
    total: int
    limit: int
    offset: int


class RecepcionItemIn(BaseModel):
    producto_id: UUID
    cantidad_recibida: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    observacion: str = Field(default="", max_length=300)


class FacturaFEL(BaseModel):
    """Encabezado de la factura de planta central; sin reglas fiscales adicionales."""

    serie: str = Field(min_length=1, max_length=50, pattern=r"\S")
    numero: str = Field(min_length=1, max_length=50, pattern=r"^[0-9]+$")
    numero_autorizacion: UUID
    fecha_emision: date
    condicion_pago: str | None = Field(default=None, max_length=150)
    serie_admin: str | None = Field(default=None, max_length=50)
    numero_admin: str | None = Field(default=None, max_length=50)

    @field_validator(
        "serie", "numero", "condicion_pago", "serie_admin", "numero_admin", mode="before"
    )
    @classmethod
    def _normalizar_texto(cls, valor: object, info):
        if isinstance(valor, str):
            valor = valor.strip()
            if info.field_name == "serie":
                return valor.upper()
            if info.field_name in {"condicion_pago", "serie_admin", "numero_admin"}:
                return valor or None
        return valor


class RecepcionCreate(FacturaFEL):
    pedido_id: UUID | None = None
    items: list[RecepcionItemIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _validar_items(self) -> Self:
        if len({i.producto_id for i in self.items}) != len(self.items):
            raise ValueError("`items` no puede repetir productos.")
        if not any(i.cantidad_recibida > 0 for i in self.items):
            raise ValueError("Debe recibir al menos un producto.")
        if self.pedido_id is None and any(i.cantidad_recibida == 0 for i in self.items):
            raise ValueError("Sin pedido, todas las cantidades deben ser positivas.")
        return self


class RecepcionOut(FacturaFEL):
    id: UUID
    pedido_id: UUID | None
    estado_pedido: EstadoPedido | None
    items: list[RecepcionItemIn]


class FacturaDuplicadaError(BaseModel):
    codigo: Literal["FACTURA_DUPLICADA"] = "FACTURA_DUPLICADA"
    mensaje: str
