"""DTOs de `GET /catalog/routes` (extensión ADR-12: filtro de rutas del dashboard)."""

from uuid import UUID

from pydantic import BaseModel


class RouteItem(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    zona: str | None = None
