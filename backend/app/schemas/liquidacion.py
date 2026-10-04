"""DTOs del módulo «Liquidación diaria de ventas» (ADR-14): unidades + dinero por ruta/vendedor."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import EstadoLiquidacion

# numeric(12,2) para cantidades y numeric(14,2) para montos (convención 3.1).
Cant = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class LineaLiquidacion(BaseModel):
    producto_id: UUID
    cantidad_cargada: Cant
    cantidad_vendida: Cant
    cantidad_devuelta: Cant = Decimal(0)
    cantidad_merma: Cant = Decimal(0)
    # Por defecto el precio vigente del catálogo.
    precio_unitario: Dinero | None = None
    # Se quedó sin producto antes de terminar la ruta: la venta es un piso de la demanda.
    agotado: bool = False
    # Obligatoria si `cantidad_cargada` difiere de la carga despachada de la ruta/fecha.
    justificacion_carga: str | None = Field(default=None, max_length=500)


class PagosLiquidacion(BaseModel):
    efectivo: Dinero = Decimal(0)
    transferencia: Dinero = Decimal(0)
    credito: Dinero = Decimal(0)
    cobro_saldos: Dinero = Decimal(0)
    gastos: Dinero = Decimal(0)
    efectivo_entregado: Dinero = Decimal(0)


class LiquidacionRequest(BaseModel):
    fecha: date
    ruta_id: UUID
    # Por defecto el vendedor asignado a la ruta.
    vendedor_id: UUID | None = None
    lineas: list[LineaLiquidacion] = Field(min_length=1)
    pagos: PagosLiquidacion = Field(default_factory=PagosLiquidacion)
    observaciones: str | None = Field(default=None, max_length=1000)


class CorreccionRequest(LiquidacionRequest):
    motivo: str = Field(min_length=5, max_length=500)


class AnulacionRequest(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def _sin_espacios(self) -> "AnulacionRequest":
        self.motivo = self.motivo.strip()
        if len(self.motivo) < 5:
            raise ValueError("El motivo debe tener al menos 5 caracteres.")
        return self


class LineaRespuesta(BaseModel):
    producto_id: UUID
    sku: str
    producto_nombre: str
    cantidad_cargada: Decimal
    cantidad_vendida: Decimal
    cantidad_devuelta: Decimal
    cantidad_merma: Decimal
    precio_unitario: Decimal
    monto_total: Decimal
    agotado: bool
    justificacion_carga: str | None = None
    # cargada − vendida − devuelta − merma (0 = la fila cuadra).
    diferencia_unidades: Decimal
    cuadra: bool


class CuadreUnidades(BaseModel):
    cargadas: Decimal
    vendidas: Decimal
    devueltas: Decimal
    merma: Decimal
    diferencia: Decimal
    cuadra: bool


class CuadreDinero(BaseModel):
    venta_total: Decimal
    total_pagos: Decimal
    diferencia_venta_pagos: Decimal
    cuadra: bool
    efectivo_esperado: Decimal
    efectivo_entregado: Decimal
    diferencia_caja: Decimal
    umbral_diferencia_caja: Decimal
    supera_umbral: bool


class LiquidacionResponse(BaseModel):
    id: UUID
    fecha: date
    ruta_id: UUID
    ruta_nombre: str
    vendedor_id: UUID
    vendedor_nombre: str
    estado: EstadoLiquidacion
    version: int
    lote_id: UUID | None = None
    lineas: list[LineaRespuesta]
    pagos: PagosLiquidacion
    cuadre_unidades: CuadreUnidades
    cuadre_dinero: CuadreDinero
    # Unidades que el flujo de inventario debe procesar por su propio camino (ADR-06).
    devolucion_esperada: Decimal
    observaciones: str | None = None
    advertencias: list[str] = Field(default_factory=list)
    alerta_id: UUID | None = None
    creado_en: datetime
    cerrado_en: datetime | None = None
    anulado_en: datetime | None = None
    anulado_motivo: str | None = None


class LiquidacionResumen(BaseModel):
    id: UUID
    fecha: date
    ruta_id: UUID
    ruta_nombre: str
    vendedor_id: UUID
    vendedor_nombre: str
    estado: EstadoLiquidacion
    version: int
    unidades_vendidas: Decimal
    venta_total: Decimal
    diferencia_caja: Decimal
    cerrado_en: datetime | None = None


class ListadoLiquidaciones(BaseModel):
    total: int
    liquidaciones: list[LiquidacionResumen]


class LineaPrecarga(BaseModel):
    producto_id: UUID
    sku: str
    producto_nombre: str
    cantidad_cargada: Decimal
    precio_unitario: Decimal


class PrecargaResponse(BaseModel):
    fecha: date
    ruta_id: UUID
    vendedor_id: UUID | None = None
    # `None` si no hay una carga despachada para esa ruta y fecha (se permite igualmente).
    carga_id: UUID | None = None
    lineas: list[LineaPrecarga]
    # Liquidación vigente (borrador o cerrada) de la ruta/fecha, si existe.
    liquidacion: LiquidacionResponse | None = None
    advertencias: list[str] = Field(default_factory=list)


class LiquidacionConfig(BaseModel):
    umbral_diferencia_caja: Dinero
