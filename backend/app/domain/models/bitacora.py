"""Bitácora de auditoría y respaldo (ADR-15): registro append-only de lo que ejecuta el sistema.

No lleva FK hacia `usuarios`: el rastro debe sobrevivir al borrado del usuario. Un trigger
(migración 0003) impide `UPDATE`, `DELETE` y `TRUNCATE`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    NivelBitacora,
    OperacionBitacora,
    OrigenBitacora,
    ResultadoBitacora,
    sql_in,
)
from app.domain.models.base import Base


class Bitacora(Base):
    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ocurrido_en: Mapped[datetime] = mapped_column(server_default=func.now())
    nivel: Mapped[str] = mapped_column(String(7))
    origen: Mapped[str] = mapped_column(String(10))
    operacion: Mapped[str] = mapped_column(String(10))
    # Función ejecutada (`services.etl_service.procesar_excel`) o `METODO /ruta` en origen http.
    accion: Mapped[str] = mapped_column(String(200))
    resultado: Mapped[str] = mapped_column(String(5))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    # Une el registro http con los de servicio de la misma petición (o del mismo ciclo del worker).
    request_id: Mapped[str | None] = mapped_column(String(36))
    metodo: Mapped[str | None] = mapped_column(String(10))
    ruta: Mapped[str | None] = mapped_column(String(300))
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    duracion_ms: Mapped[int | None]
    # Argumentos saneados (sin contraseñas/tokens, truncados).
    parametros: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    codigo_error: Mapped[str | None] = mapped_column(String(60))
    mensaje: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(sql_in("nivel", NivelBitacora), name="nivel_valido"),
        CheckConstraint(sql_in("origen", OrigenBitacora), name="origen_valido"),
        CheckConstraint(sql_in("operacion", OperacionBitacora), name="operacion_valida"),
        CheckConstraint(sql_in("resultado", ResultadoBitacora), name="resultado_valido"),
        Index("ix_bitacora_ocurrido_en", "ocurrido_en"),
        Index("ix_bitacora_usuario_id", "usuario_id"),
        Index("ix_bitacora_accion", "accion"),
        Index("ix_bitacora_request_id", "request_id"),
    )
