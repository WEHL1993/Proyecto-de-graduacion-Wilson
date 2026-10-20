"""DTOs de RBAC en base de datos (ADR-19): menú, matriz rol×permiso y acceso por usuario."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import ColorRol


class PantallaMenu(BaseModel):
    """Entrada del menú lateral autorizada para el usuario."""

    clave: str
    etiqueta: str
    ruta: str
    ruta_prefijo: str | None = None
    grupo: str
    orden: int


class AccesoSesion(BaseModel):
    """Lo que el frontend necesita para pintar la sesión: roles, permisos y menú vigentes."""

    id: UUID
    nombre_completo: str
    roles: list[str]
    permisos: list[str]
    menu: list[PantallaMenu]
    pantalla_inicio: str | None = Field(
        default=None, description="Ruta a la que se entra tras iniciar sesión."
    )
    debe_cambiar_password: bool = Field(
        default=False, description="La contraseña es temporal: debe cambiarse antes de operar."
    )


class RolMatriz(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None
    activo: bool
    es_sistema: bool
    requiere_proveedor: bool
    color: ColorRol
    pantalla_inicio: str | None = Field(default=None, description="Clave de la pantalla.")
    total_usuarios: int
    permisos: list[str] = Field(description="Códigos de permiso asignados al rol.")


class PermisoMatriz(BaseModel):
    id: int
    codigo: str
    descripcion: str | None = None
    modulo: str
    activo: bool


class PantallaMatriz(BaseModel):
    id: int
    clave: str
    etiqueta: str
    ruta: str
    grupo: str
    orden: int
    activo: bool
    permisos: list[str] = Field(description="La pantalla se habilita con CUALQUIERA de estos.")


class MatrizAcceso(BaseModel):
    roles: list[RolMatriz]
    permisos: list[PermisoMatriz]
    pantallas: list[PantallaMatriz]


class RolPermisosUpdate(BaseModel):
    permisos: list[str] = Field(description="Conjunto completo de códigos de permiso del rol.")


class RolUpdate(BaseModel):
    descripcion: str | None = Field(default=None, max_length=255)
    activo: bool | None = None
    color: ColorRol | None = None
    pantalla_inicio: str | None = Field(
        default=None, description="Clave de pantalla; `null` explícito la quita."
    )


class PantallaAcceso(BaseModel):
    clave: str
    etiqueta: str
    ruta: str
    grupo: str
    autorizada: bool
    via_permisos: list[str] = Field(description="Permisos del usuario que la habilitan.")


class AccesoUsuario(BaseModel):
    usuario_id: UUID
    nombre_completo: str
    activo: bool
    roles: list[str]
    permisos: list[str]
    pantallas: list[PantallaAcceso]
