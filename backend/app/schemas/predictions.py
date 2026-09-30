"""DTOs de `POST /predictions/demand` (sección 4 de `openapi.contract.yaml`)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DemandRequest(BaseModel):
    producto_ids: list[UUID] = Field(min_length=1, max_length=200)
    ruta_id: UUID | None = Field(
        default=None, description="Si se omite, la demanda es agregada (suma de todas las rutas)"
    )
    fecha_base: date | None = Field(default=None, description="Por defecto hoy")
    horizonte_dias: int = Field(ge=1, le=30)
    incluir_intervalo: bool = True
    # Extensión al contrato (ADR-11): guarda el resultado en `pronosticos_demanda`.
    persistir: bool = Field(default=False, description="Guarda los pronósticos en la BD")


class DemandPoint(BaseModel):
    fecha_objetivo: date
    demanda_predicha: float
    limite_inferior: float | None = None
    limite_superior: float | None = None


class DemandProductForecast(BaseModel):
    producto_id: UUID
    serie: list[DemandPoint]


class DemandModelInfo(BaseModel):
    id: UUID
    algoritmo: str
    version: str


class DemandResponse(BaseModel):
    modelo: DemandModelInfo
    generado_en: datetime
    pronosticos: list[DemandProductForecast]
