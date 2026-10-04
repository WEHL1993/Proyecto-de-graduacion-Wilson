"""Ensamblado de la aplicación FastAPI."""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core import contexto
from app.core.config import get_settings
from app.core.contexto import ContextoAuditoria
from app.core.errors import AppError, app_error_handler
from app.core.security import decode_access_token
from app.domain.enums import OrigenBitacora
from app.services import bitacora_service

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Contrato del prototipo de tesis. Autenticación JWT y control de acceso RBAC.",
    servers=[{"url": "http://localhost:8000", "description": "Desarrollo local"}],
)

app.add_exception_handler(AppError, app_error_handler)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_RUTAS_SIN_BITACORA = ("/health", "/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def bitacora_http(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
    """Un registro de bitácora por petición (ADR-15) y contexto (usuario, IP, request id) para
    los registros de servicio de esa misma petición."""
    ruta = request.url.path
    if request.method == "OPTIONS" or ruta in _RUTAS_SIN_BITACORA:
        return await call_next(request)
    ctx = ContextoAuditoria(
        origen=OrigenBitacora.HTTP.value,
        request_id=request.headers.get("x-request-id") or str(uuid.uuid4()),
        usuario_id=_usuario_del_token(request),
        ip=request.client.host if request.client else None,
        metodo=request.method,
        ruta=ruta,
    )
    token = contexto.establecer(ctx)
    inicio = time.perf_counter()
    status_code, error = 500, None
    try:
        respuesta = await call_next(request)
        status_code = respuesta.status_code
        respuesta.headers["X-Request-ID"] = ctx.request_id
        return respuesta
    except Exception as exc:
        error = exc
        raise
    finally:
        await run_in_threadpool(
            bitacora_service.registrar_http,
            metodo=request.method,
            ruta=ruta,
            status_code=status_code,
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            usuario_id=ctx.usuario_id,
            exc=error,
        )
        contexto.restablecer(token)


def _usuario_del_token(request: Request) -> uuid.UUID | None:
    """Usuario del JWT si es válido; la autenticación real sigue en `api/deps.py`."""
    esquema, _, credencial = request.headers.get("authorization", "").partition(" ")
    if esquema.lower() != "bearer" or not credencial:
        return None
    try:
        return uuid.UUID(decode_access_token(credencial)["sub"])
    except Exception:  # noqa: BLE001 - token ausente/ inválido: lo rechaza la dependencia
        return None


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"], summary="Liveness del servicio")
def health() -> dict[str, str]:
    """Usado por el healthcheck de Docker; no consulta la base de datos."""
    return {"status": "ok"}
