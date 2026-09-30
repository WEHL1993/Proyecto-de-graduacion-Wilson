"""DTOs de `GET /alerts` (extensión ADR-12: bandeja de alertas para el frontend)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import EstadoAlerta, Severidad, TipoAlerta


class AlertItem(BaseModel):
    id: UUID
    tipo: TipoAlerta
    severidad: Severidad
    mensaje: str
    estado: EstadoAlerta
    producto_id: UUID | None = None
    modelo_id: UUID | None = None
    creada_en: datetime


class AlertList(BaseModel):
    total: int
    alertas: list[AlertItem]
