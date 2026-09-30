"""DTOs de `POST /routes/load-plans` (sección 4 de `openapi.contract.yaml`)."""

from datetime import date
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import EstadoCarga


class AjusteCarga(BaseModel):
    producto_id: UUID
    cantidad_aprobada: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class LoadPlanRequest(BaseModel):
    accion: Literal["generar", "aprobar", "rechazar"]
    ruta_id: UUID | None = Field(default=None, description="Obligatorio si accion=generar")
    fecha_operacion: date | None = Field(default=None, description="Obligatorio si accion=generar")
    carga_id: UUID | None = Field(
        default=None, description="Obligatorio si accion=aprobar|rechazar"
    )
    ajustes: list[AjusteCarga] | None = Field(
        default=None, description="Cantidades aprobadas editadas (solo accion=aprobar)"
    )
    motivo_rechazo: str | None = Field(default=None, description="Obligatorio si accion=rechazar")
    observaciones: str | None = None

    @model_validator(mode="after")
    def _campos_por_accion(self) -> Self:
        if self.accion == "generar":
            if self.ruta_id is None or self.fecha_operacion is None:
                raise ValueError("accion=generar exige `ruta_id` y `fecha_operacion`.")
        elif self.carga_id is None:
            raise ValueError(f"accion={self.accion} exige `carga_id`.")
        if self.accion == "rechazar" and not (self.motivo_rechazo or "").strip():
            raise ValueError("accion=rechazar exige `motivo_rechazo`.")
        if self.accion != "aprobar" and self.ajustes:
            raise ValueError("`ajustes` solo aplica a accion=aprobar.")
        if self.ajustes and len({a.producto_id for a in self.ajustes}) != len(self.ajustes):
            raise ValueError("`ajustes` no puede repetir productos.")
        return self


class LoadPlanItem(BaseModel):
    producto_id: UUID
    sku: str
    cantidad_predicha: Decimal
    stock_disponible: Decimal = Field(description="Stock disponible al generar el plan")
    cantidad_sugerida: Decimal
    cantidad_aprobada: Decimal | None = Field(
        default=None, description="Nula hasta que el plan se aprueba"
    )
    ajustado_por_stock: bool


class LoadPlanResponse(BaseModel):
    carga_id: UUID
    ruta_id: UUID
    fecha_operacion: date
    estado: EstadoCarga
    modelo_id: UUID
    items: list[LoadPlanItem]
    alertas_generadas: list[UUID] = Field(default_factory=list)
