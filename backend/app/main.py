"""Ensamblado de la aplicación FastAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler

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

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["Health"], summary="Liveness del servicio")
def health() -> dict[str, str]:
    """Usado por el healthcheck de Docker; no consulta la base de datos."""
    return {"status": "ok"}
