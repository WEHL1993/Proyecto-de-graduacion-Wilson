"""DTOs de reportes gerenciales (`/reports`, Módulo 7). Permiso `reportes:leer` (ADR-13)."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class TipoReporte(StrEnum):
    CONSOLIDADO = "consolidado"
    ROTACION = "rotacion"
    COMISIONES = "comisiones"
    VENTAS_PROYECCION = "ventas_proyeccion"


class FormatoReporte(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


# ---------------------------------------------------------------- rotación y quiebres
class RotacionRuta(BaseModel):
    ruta_id: UUID
    ruta_codigo: str
    ruta_nombre: str
    unidades_vendidas: Decimal
    monto_vendido: Decimal
    costo_ventas: Decimal
    # costo de ventas de la ruta / valor del inventario actual (aporte a la rotación global).
    rotacion: Decimal | None = None
    cargas: int
    lineas_carga: int
    lineas_ajustadas: int
    # % de líneas de carga limitadas por stock (`ajustado_por_stock`).
    indice_quiebre: Decimal | None = None
    unidades_no_cubiertas: Decimal


class RotacionReporte(BaseModel):
    desde: date
    hasta: date
    valor_inventario: Decimal
    costo_ventas_total: Decimal
    # costo de ventas del periodo / valor del inventario actual.
    rotacion_global: Decimal | None = None
    dias_inventario: Decimal | None = None
    indice_quiebre_global: Decimal | None = None
    rutas: list[RotacionRuta]


# ---------------------------------------------------------------- comisiones
class ComisionVendedor(BaseModel):
    vendedor_id: UUID
    vendedor: str
    periodo: str
    ventas_registradas: int
    monto_vendido: Decimal
    comision_total: Decimal
    porcentaje_efectivo: Decimal | None = None


class ComisionReporte(BaseModel):
    periodo_desde: str
    periodo_hasta: str
    total_vendido: Decimal
    total_comisiones: Decimal
    liquidaciones: list[ComisionVendedor]


# ---------------------------------------------------------------- real vs proyectado
class VentaProyeccionRuta(BaseModel):
    ruta_id: UUID
    ruta_codigo: str
    ruta_nombre: str
    real: Decimal
    proyectada: Decimal
    # (real - proyectada) / proyectada, en %.
    desviacion_pct: Decimal | None = None


class VentaProyeccionDia(BaseModel):
    fecha: date
    real: Decimal
    proyectada: Decimal


class VentasProyeccionReporte(BaseModel):
    desde: date
    hasta: date
    total_real: Decimal
    total_proyectado: Decimal
    rutas: list[VentaProyeccionRuta]
    serie: list[VentaProyeccionDia]
