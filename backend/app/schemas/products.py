"""DTOs del CRUD de productos (`/products`) con baja lógica (ADR-16)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProductoCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=2, max_length=200)
    categoria_id: UUID
    proveedor_id: UUID | None = None
    unidad_medida: str = Field(default="unidad", min_length=1, max_length=20)
    precio_venta: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    costo_unitario: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    stock_minimo: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class ProductoUpdate(BaseModel):
    """Actualización parcial. No modifica existencias (usar `POST /inventory/adjustments`) ni el
    estado (usar `DELETE` / `POST .../reactivate`)."""

    sku: str | None = Field(default=None, min_length=1, max_length=30)
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    categoria_id: UUID | None = None
    proveedor_id: UUID | None = None
    unidad_medida: str | None = Field(default=None, min_length=1, max_length=20)
    precio_venta: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    costo_unitario: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    stock_minimo: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class ProductoOut(BaseModel):
    id: UUID
    sku: str
    nombre: str
    categoria_id: UUID
    categoria: str
    proveedor_id: UUID | None = None
    unidad_medida: str
    precio_venta: Decimal
    costo_unitario: Decimal
    stock_minimo: Decimal
    activo: bool
    stock_actual: Decimal
    stock_reservado: Decimal
    stock_disponible: Decimal
    creado_en: datetime


class ProductoPage(BaseModel):
    items: list[ProductoOut]
    total: int
    limit: int
    offset: int
