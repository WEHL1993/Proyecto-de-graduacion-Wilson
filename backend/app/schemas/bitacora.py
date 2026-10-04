"""DTOs de la consulta de la bitácora de auditoría (ADR-15)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BitacoraItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ocurrido_en: datetime
    nivel: str
    origen: str
    operacion: str
    accion: str
    resultado: str
    usuario_id: UUID | None
    ip: str | None
    request_id: str | None
    metodo: str | None
    ruta: str | None
    status_code: int | None
    duracion_ms: int | None
    parametros: dict[str, Any] | None
    codigo_error: str | None
    mensaje: str | None


class BitacoraPage(BaseModel):
    total: int
    registros: list[BitacoraItem]
