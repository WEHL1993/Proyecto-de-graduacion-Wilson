"""DTOs de la gestión administrativa de usuarios (`/users`, permiso `usuarios:gestionar`)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RolItem(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None


class RutaAsignada(BaseModel):
    id: UUID
    codigo: str
    nombre: str


class UsuarioOut(BaseModel):
    id: UUID
    email: EmailStr
    nombre_completo: str
    activo: bool
    roles: list[str]
    rutas: list[RutaAsignada]
    proveedor_id: UUID | None = None
    ultimo_login: datetime | None = None
    creado_en: datetime


class UsuarioPage(BaseModel):
    total: int
    usuarios: list[UsuarioOut]


class UsuarioCreate(BaseModel):
    email: EmailStr
    nombre_completo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    roles: list[str] = Field(min_length=1, description="Nombres de rol (`GET /users/roles`)")
    ruta_ids: list[UUID] = Field(default_factory=list)
    proveedor_id: UUID | None = Field(default=None, description="Obligatorio con rol Proveedor")
    activo: bool = True


class UsuarioUpdate(BaseModel):
    """Actualización parcial: solo se modifican los campos presentes."""

    nombre_completo: str | None = Field(default=None, min_length=3, max_length=150)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    roles: list[str] | None = Field(default=None, min_length=1)
    ruta_ids: list[UUID] | None = None
    proveedor_id: UUID | None = None


class UsuarioEstado(BaseModel):
    activo: bool
