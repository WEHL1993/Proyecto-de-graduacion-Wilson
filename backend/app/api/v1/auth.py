"""Endpoints de autenticación (`POST /auth/login`)."""

from fastapi import APIRouter

from app.api.deps import DBSession
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse, summary="Autenticación y emisión de JWT")
def login(datos: LoginRequest, db: DBSession) -> TokenResponse:
    return auth_service.login(db, datos)
