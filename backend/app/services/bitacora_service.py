"""Bitácora de auditoría y respaldo (ADR-15).

- `@auditar` envuelve cada caso de uso (función pública de `services/` y jobs del Worker) y deja
  un registro con quién, qué, argumentos saneados, resultado y duración, también si falla.
- `registrar_http` lo usa el middleware para cada petición (incluye 401/403 que no llegan a un
  servicio).
- Los registros se escriben en una sesión **independiente** (conexión propia, `commit` propio):
  un `rollback` del caso de uso no borra su rastro. Un fallo al registrar nunca rompe la operación
  de negocio: se informa por el logger `app.bitacora`.
"""

import functools
import inspect
import logging
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar, overload

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import contexto
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import AppError
from app.domain.enums import NivelBitacora, OperacionBitacora, OrigenBitacora, ResultadoBitacora
from app.repositories import bitacora_repo
from app.schemas.auth import UsuarioAutenticado
from app.schemas.bitacora import BitacoraItem, BitacoraPage

logger = logging.getLogger("app.bitacora")

F = TypeVar("F", bound=Callable[..., Any])

_SENSIBLE = re.compile(r"pass|clave|contrase|secret|token|hash", re.IGNORECASE)
_PREFIJOS_LECTURA = (
    "listar",
    "obtener",
    "consultar",
    "estado",
    "tipos_",
    "sugerir",
    "precargar",
    "predecir",
    "rotacion",
    "ventas_vs",
    "liquidacion_comisiones",
    "exportar",
    "gestionar",
)
_MAX_TEXTO = 200
_MAX_ITEMS = 20
_MAX_PROFUNDIDAD = 3
_ARGUMENTOS_USUARIO = ("usuario_id", "actor_id", "creado_por", "solicitado_por")


# ------------------------------------------------------------------ saneamiento
def sanear(valor: Any, clave: str = "", nivel: int = 0) -> Any:
    """Convierte un argumento a JSON seguro: sin secretos, truncado y sin objetos pesados."""
    if clave and _SENSIBLE.search(clave):
        return "***"
    if valor is None or isinstance(valor, bool | int | float):
        return valor
    if isinstance(valor, str):
        return valor if len(valor) <= _MAX_TEXTO else valor[:_MAX_TEXTO] + "…"
    if isinstance(valor, Enum):
        return sanear(valor.value, clave, nivel)
    if isinstance(valor, uuid.UUID | date | datetime | Decimal):
        return str(valor)
    if isinstance(valor, bytes | bytearray):
        return f"<{len(valor)} bytes>"
    if isinstance(valor, BaseModel):
        try:
            return sanear(valor.model_dump(mode="json"), clave, nivel)
        except Exception:  # noqa: BLE001 - un DTO raro no debe impedir el registro
            return f"<{type(valor).__name__}>"
    if isinstance(valor, Mapping):
        if nivel >= _MAX_PROFUNDIDAD:
            return f"<{type(valor).__name__}>"
        return {str(k): sanear(v, str(k), nivel + 1) for k, v in list(valor.items())[:_MAX_ITEMS]}
    if isinstance(valor, list | tuple | set | frozenset):
        if nivel >= _MAX_PROFUNDIDAD:
            return f"<{type(valor).__name__}[{len(valor)}]>"
        items = [sanear(v, clave, nivel + 1) for v in list(valor)[:_MAX_ITEMS]]
        if len(valor) > _MAX_ITEMS:
            items.append(f"… (+{len(valor) - _MAX_ITEMS})")
        return items
    return f"<{type(valor).__name__}>"


# ------------------------------------------------------------------ escritura
def _nivel(exc: Exception | None) -> NivelBitacora:
    if exc is None:
        return NivelBitacora.INFO
    if isinstance(exc, AppError) and exc.status_code < 500:
        return NivelBitacora.WARNING
    return NivelBitacora.ERROR


def _insertar(bind: Any, campos: dict[str, Any]) -> None:
    """`bind` es el Engine (producción) o la Connection de la prueba (savepoint, se revierte)."""
    with Session(bind=bind, join_transaction_mode="create_savepoint") as sesion:
        bitacora_repo.insertar(sesion, **campos)
        sesion.commit()


def registrar(
    db: Session | None,
    *,
    accion: str,
    operacion: OperacionBitacora,
    resultado: ResultadoBitacora,
    nivel: NivelBitacora,
    origen: OrigenBitacora | None = None,
    usuario_id: uuid.UUID | None = None,
    parametros: dict[str, Any] | None = None,
    duracion_ms: int | None = None,
    status_code: int | None = None,
    codigo_error: str | None = None,
    mensaje: str | None = None,
) -> None:
    """Inserta un registro. Nunca lanza: ante un fallo lo deja en el logger `app.bitacora`."""
    if not get_settings().bitacora_habilitada:
        return
    ctx = contexto.obtener()
    if origen is None:  # el origen `http` es solo de las filas del middleware
        en_worker = ctx is not None and ctx.origen == OrigenBitacora.WORKER.value
        origen = OrigenBitacora.WORKER if en_worker else OrigenBitacora.SERVICIO
    try:
        campos = {
            "nivel": nivel.value,
            "origen": origen.value,
            "operacion": operacion.value,
            "accion": accion[:200],
            "resultado": resultado.value,
            "usuario_id": usuario_id or (ctx.usuario_id if ctx else None),
            "ip": ctx.ip if ctx else None,
            "request_id": ctx.request_id if ctx else None,
            "metodo": ctx.metodo if ctx else None,
            "ruta": ctx.ruta[:300] if ctx and ctx.ruta else None,
            "status_code": status_code,
            "duracion_ms": duracion_ms,
            "parametros": parametros,
            "codigo_error": codigo_error,
            "mensaje": mensaje[:2000] if mensaje else None,
        }
        _insertar(db.get_bind() if db is not None else get_engine(), campos)
    except Exception:
        logger.exception("No se pudo escribir en la bitácora: accion=%s", accion)


def registrar_http(
    *,
    metodo: str,
    ruta: str,
    status_code: int,
    duracion_ms: int,
    usuario_id: uuid.UUID | None,
    exc: Exception | None = None,
) -> None:
    """Un registro por petición HTTP; `status >= 400` queda como WARNING/ERROR."""
    if exc is not None or status_code >= 500:
        nivel, resultado = NivelBitacora.ERROR, ResultadoBitacora.ERROR
    elif status_code >= 400:
        nivel, resultado = NivelBitacora.WARNING, ResultadoBitacora.ERROR
    else:
        nivel, resultado = NivelBitacora.INFO, ResultadoBitacora.EXITO
    registrar(
        None,
        accion=f"{metodo} {ruta}",
        operacion=(
            OperacionBitacora.LECTURA if metodo in ("GET", "HEAD") else OperacionBitacora.ESCRITURA
        ),
        resultado=resultado,
        nivel=nivel,
        origen=OrigenBitacora.HTTP,
        usuario_id=usuario_id,
        duracion_ms=duracion_ms,
        status_code=status_code,
        mensaje=f"{type(exc).__name__}: {exc}" if exc is not None else None,
    )


# ------------------------------------------------------------------ decorador
def _usuario_de(argumentos: Mapping[str, Any]) -> uuid.UUID | None:
    for valor in argumentos.values():
        if isinstance(valor, UsuarioAutenticado):
            return valor.id
    for nombre in _ARGUMENTOS_USUARIO:
        valor = argumentos.get(nombre)
        if isinstance(valor, uuid.UUID):
            return valor
    return None


def _operacion(nombre: str) -> OperacionBitacora:
    if nombre.startswith(_PREFIJOS_LECTURA):
        return OperacionBitacora.LECTURA
    return OperacionBitacora.ESCRITURA


@overload
def auditar(funcion: F) -> F: ...
@overload
def auditar(*, operacion: OperacionBitacora | None = None) -> Callable[[F], F]: ...
def auditar(funcion: F | None = None, *, operacion: OperacionBitacora | None = None):
    """Registra en la bitácora cada ejecución de la función (éxito o error) y relanza el error.

    Uso: `@auditar` o `@auditar(operacion=OperacionBitacora.LECTURA)` (por defecto se infiere
    del nombre: `listar_*`, `obtener_*`, `consultar_*`... son lecturas)."""

    def decorar(func: F) -> F:
        firma = inspect.signature(func)
        accion = f"{func.__module__.removeprefix('app.')}.{func.__qualname__}"
        tipo = operacion or _operacion(func.__name__)

        @functools.wraps(func)
        def envoltura(*args: Any, **kwargs: Any) -> Any:
            inicio = time.perf_counter()
            try:
                resultado = func(*args, **kwargs)
            except Exception as exc:
                _auditar_llamada(func, firma, accion, tipo, args, kwargs, inicio, None, exc)
                raise
            _auditar_llamada(func, firma, accion, tipo, args, kwargs, inicio, resultado, None)
            return resultado

        return envoltura  # type: ignore[return-value]

    return decorar(funcion) if funcion is not None else decorar


def _auditar_llamada(
    func: Callable[..., Any],
    firma: inspect.Signature,
    accion: str,
    tipo: OperacionBitacora,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    inicio: float,
    resultado: Any,
    exc: Exception | None,
) -> None:
    if not get_settings().bitacora_habilitada:
        return
    try:
        enlazados = dict(firma.bind_partial(*args, **kwargs).arguments)
        db = next((v for v in enlazados.values() if isinstance(v, Session)), None)
        usuario_id = _usuario_de(enlazados)
        if usuario_id is None:  # p. ej. login: el usuario sale del resultado
            usuario_id = getattr(getattr(resultado, "usuario", None), "id", None)
        parametros = {
            nombre: sanear(valor, nombre)
            for nombre, valor in enlazados.items()
            if not isinstance(valor, Session)
        }
        codigo = None
        if exc is not None:
            codigo = exc.codigo if isinstance(exc, AppError) else type(exc).__name__
        registrar(
            db,
            accion=accion,
            operacion=tipo,
            resultado=ResultadoBitacora.ERROR if exc else ResultadoBitacora.EXITO,
            nivel=_nivel(exc),
            usuario_id=usuario_id if isinstance(usuario_id, uuid.UUID) else None,
            parametros=parametros,
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            codigo_error=codigo,
            mensaje=str(exc) if exc else None,
        )
    except Exception:
        logger.exception("No se pudo auditar %s", func.__qualname__)


# ------------------------------------------------------------------ consulta
def listar(
    db: Session,
    *,
    desde: datetime | None,
    hasta: datetime | None,
    usuario_id: uuid.UUID | None,
    accion: str | None,
    origen: str | None,
    resultado: str | None,
    request_id: str | None,
    limit: int,
    offset: int,
) -> BitacoraPage:
    filas, total = bitacora_repo.listar(
        db,
        desde=desde,
        hasta=hasta,
        usuario_id=usuario_id,
        accion=accion,
        origen=origen,
        resultado=resultado,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
    return BitacoraPage(total=total, registros=[BitacoraItem.model_validate(f) for f in filas])
