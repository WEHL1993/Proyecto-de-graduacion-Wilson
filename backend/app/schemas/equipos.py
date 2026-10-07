"""DTOs de rutas administrables, empleados y equipos de ruta (M02, ADR-18)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import RolEnRuta


# ------------------------------------------------------------------ rutas
class RutaCreate(BaseModel):
    """El `codigo` se normaliza a mayúsculas y no se modifica después (lo usa el ETL)."""

    codigo: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=2, max_length=100)
    zona: str | None = Field(default=None, max_length=100)
    vendedor_id: UUID | None = None


class RutaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    zona: str | None = Field(default=None, max_length=100)
    vendedor_id: UUID | None = None


class RutaAdminOut(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    zona: str | None = None
    vendedor_id: UUID | None = None
    activa: bool
    integrantes: int
    suma_porcentaje: Decimal
    equipo_completo: bool


# ------------------------------------------------------------------ empleados
class EmpleadoCreate(BaseModel):
    nombre_completo: str = Field(min_length=2, max_length=150)
    usuario_id: UUID | None = None


class EmpleadoUpdate(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=2, max_length=150)
    usuario_id: UUID | None = None


class EmpleadoOut(BaseModel):
    id: UUID
    nombre_completo: str
    usuario_id: UUID | None = None
    activo: bool
    creado_en: datetime


class EmpleadoPage(BaseModel):
    items: list[EmpleadoOut]
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ equipo de ruta
class IntegranteIn(BaseModel):
    empleado_id: UUID
    rol_en_ruta: RolEnRuta
    porcentaje_reparto: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class EquipoReemplazo(BaseModel):
    """Reemplaza el equipo vigente: las vigencias anteriores se cierran, no se borran."""

    integrantes: list[IntegranteIn] = Field(min_length=1, max_length=20)
    vigente_desde: date | None = Field(
        default=None, description="Inicio de la nueva vigencia; por defecto, hoy (UTC)."
    )


class IntegranteOut(BaseModel):
    empleado_id: UUID
    nombre_completo: str
    rol_en_ruta: RolEnRuta
    porcentaje_reparto: Decimal
    vigente_desde: date
    vigente_hasta: date | None = None


class EquipoRutaOut(BaseModel):
    ruta_id: UUID
    integrantes: list[IntegranteOut]
    suma_porcentaje: Decimal
    suma_100: bool
    tiene_vendedor: bool
    historial: list[IntegranteOut]


class RutaEquipoIncompleto(BaseModel):
    ruta_id: UUID
    codigo: str
    nombre: str
    integrantes: int
    suma_porcentaje: Decimal
    tiene_vendedor: bool
    motivos: list[str]


class RutaDesalineada(BaseModel):
    """Dos fuentes de verdad del vendedor (ADR-18); se resuelve en M05/M06."""

    ruta_id: UUID
    codigo: str
    nombre: str
    vendedor_id_ruta: UUID | None = None
    empleado_vendedor_id: UUID
    empleado_vendedor: str
    usuario_id_empleado: UUID | None = None
