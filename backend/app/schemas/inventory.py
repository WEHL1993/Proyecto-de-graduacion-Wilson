"""DTOs de lectura de existencias y kardex (`/inventory`)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import ReferenciaTipo, TipoMovimiento


class StockItem(BaseModel):
    producto_id: UUID
    sku: str
    nombre: str
    stock_actual: Decimal
    stock_reservado: Decimal
    stock_disponible: Decimal
    stock_minimo: Decimal
    bajo_minimo: bool


class StockPage(BaseModel):
    items: list[StockItem]
    total: int
    limit: int
    offset: int


class KardexEntry(BaseModel):
    id: int
    producto_id: UUID
    tipo_movimiento: TipoMovimiento
    cantidad: Decimal
    saldo_resultante: Decimal
    referencia_tipo: ReferenciaTipo | None = None
    referencia_id: UUID | None = None
    usuario_id: UUID | None = None
    fecha_movimiento: datetime


class KardexPage(BaseModel):
    items: list[KardexEntry]
    total: int
    limit: int
    offset: int
