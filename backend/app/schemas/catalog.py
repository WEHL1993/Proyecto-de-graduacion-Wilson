"""DTOs de los catálogos de apoyo al frontend (`/catalog/*`): rutas, categorías y proveedores."""

from uuid import UUID

from pydantic import BaseModel


class RouteItem(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    zona: str | None = None


class CategoriaItem(BaseModel):
    id: UUID
    nombre: str


class ProveedorItem(BaseModel):
    id: UUID
    nombre: str
