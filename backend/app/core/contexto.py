"""Contexto de auditoría por petición/ciclo (`contextvars`): quién, desde dónde y con qué id.

Lo fija el middleware HTTP (origen `http`) o el planificador del Worker (origen `worker`); el
decorador `@auditar` lo lee para completar cada registro de la bitácora. Se propaga a los
endpoints síncronos porque Starlette copia el contexto al hilo del threadpool.
"""

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextoAuditoria:
    origen: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    usuario_id: uuid.UUID | None = None
    ip: str | None = None
    metodo: str | None = None
    ruta: str | None = None


_contexto: ContextVar[ContextoAuditoria | None] = ContextVar("contexto_auditoria", default=None)


def establecer(contexto: ContextoAuditoria) -> Token[ContextoAuditoria | None]:
    return _contexto.set(contexto)


def restablecer(token: Token[ContextoAuditoria | None]) -> None:
    _contexto.reset(token)


def obtener() -> ContextoAuditoria | None:
    return _contexto.get()
