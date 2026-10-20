"""DTOs del módulo de autenticación (sección 4 de `openapi.contract.yaml`)."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.rbac import PantallaMenu


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class CambiarPasswordRequest(BaseModel):
    password_actual: str = Field(min_length=8, max_length=128)
    password_nueva: str = Field(min_length=8, max_length=128)


class UsuarioToken(BaseModel):
    id: UUID
    nombre_completo: str
    roles: list[str]
    permisos: list[str]
    menu: list[PantallaMenu] = []
    pantalla_inicio: str | None = None
    debe_cambiar_password: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioToken


class UsuarioAutenticado(BaseModel):
    """Usuario de la petición: identidad del JWT y roles/permisos vigentes (ADR-19)."""

    id: UUID
    roles: list[str]
    permisos: list[str]
