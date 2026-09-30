"""DTOs del módulo de autenticación (sección 4 de `openapi.contract.yaml`)."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UsuarioToken(BaseModel):
    id: UUID
    nombre_completo: str
    roles: list[str]
    permisos: list[str]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioToken


class UsuarioAutenticado(BaseModel):
    """Claims del JWT ya decodificado (ADR-05: sin consulta a BD en cada request)."""

    id: UUID
    roles: list[str]
    permisos: list[str]
