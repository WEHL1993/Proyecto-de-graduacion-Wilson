"""Base declarativa, convención de nombres y tipos/columnas reutilizables.

Convenciones (sección 3.1 de la especificación):
- PK `uuid` con `gen_random_uuid()` para entidades de negocio; `bigint IDENTITY` para alto volumen.
- `timestamptz` en UTC para marcas de tiempo; `date` para fechas de negocio.
- Montos numeric(14,2); cantidades numeric(12,2); porcentajes de error numeric(7,3).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, MetaData, Numeric, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Tipos anotados reutilizables
Monto = Annotated[Decimal, mapped_column(Numeric(14, 2))]
Cantidad = Annotated[Decimal, mapped_column(Numeric(12, 2))]
PorcentajeError = Annotated[Decimal, mapped_column(Numeric(7, 3))]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        sort_order=-10,
    )


class CreadoEnMixin:
    creado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditoriaMixin(CreadoEnMixin):
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
