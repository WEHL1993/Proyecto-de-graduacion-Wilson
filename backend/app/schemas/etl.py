"""DTOs del módulo ETL (`POST /etl/upload-excel`, sección 4 de `openapi.contract.yaml`)."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import FuenteReentrenamiento

# Contrato: máx. 20 MB por archivo.
TAMANO_MAXIMO_BYTES = 20 * 1024 * 1024
# Tope de errores detallados que se persisten y devuelven (el total real va en `total_errores`).
MAX_ERRORES_DETALLADOS = 1000


class ModoCarga(StrEnum):
    ESTRICTO = "estricto"
    PARCIAL = "parcial"


class CodigoErrorEtl(StrEnum):
    COLUMNAS_FALTANTES = "COLUMNAS_FALTANTES"
    TIPOS_INVALIDOS = "TIPOS_INVALIDOS"
    DATOS_INVALIDOS = "DATOS_INVALIDOS"


class ErrorFila(BaseModel):
    """Error de validación localizado por fila/columna (fila = número de fila en Excel)."""

    fila: int
    columna: str
    valor: str | None = None
    mensaje: str
    # Extensión al contrato: en libros con varias hojas (formato ancho) la fila sola es ambigua.
    hoja: str | None = None


class RangoFechas(BaseModel):
    desde: date
    hasta: date


class EtlResult(BaseModel):
    lote_id: UUID
    estado: Literal["cargado", "rechazado"]
    filas_totales: int
    filas_validas: int
    filas_rechazadas: int
    rango_fechas: RangoFechas | None = None
    advertencias: list[str] = Field(default_factory=list)


class EtlValidationError(BaseModel):
    codigo: CodigoErrorEtl
    lote_id: UUID
    errores: list[ErrorFila]
    # Extensión al contrato: `errores` se trunca en MAX_ERRORES_DETALLADOS.
    total_errores: int


class LoteItem(BaseModel):
    """Fila del historial de lotes (`etl_lotes`) para la auditoría de cargas."""

    id: UUID
    archivo_nombre: str
    estado: str
    filas_totales: int
    filas_validas: int
    filas_rechazadas: int
    cargado_por: str
    creado_en: datetime


class LotePage(BaseModel):
    total: int
    lotes: list[LoteItem]


class EtlConfig(BaseModel):
    """Política de datos del modelo (ADR-14)."""

    carga_excel_habilitada: bool
    fuente_reentrenamiento: FuenteReentrenamiento
