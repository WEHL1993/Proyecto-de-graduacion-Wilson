"""Endpoints de autenticación (`POST /auth/login`)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.auth import CambiarPasswordRequest, LoginRequest, TokenResponse
from app.schemas.rbac import AccesoSesion
from app.services import auth_service, rbac_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse, summary="Autenticación y emisión de JWT")
def login(datos: LoginRequest, db: DBSession) -> TokenResponse:
    return auth_service.login(db, datos)


@router.post(
    "/cambiar-password",
    status_code=204,
    summary="Cambio de contraseña propia",
    description=(
        "Cualquier usuario autenticado cambia su contraseña indicando la actual. Es el paso "
        "obligatorio cuando un administrador fijó una contraseña temporal."
    ),
)
def cambiar_password(datos: CambiarPasswordRequest, usuario: CurrentUser, db: DBSession) -> None:
    auth_service.cambiar_password(db, usuario.id, datos)


@router.get(
    "/me",
    response_model=AccesoSesion,
    summary="Sesión vigente: roles, permisos y menú",
    description=(
        "Lee de la BD los roles y permisos actuales de quien consulta y el menú de pantallas "
        "autorizadas (ADR-19). El frontend lo refresca para reflejar cambios de la matriz."
    ),
)
def sesion_vigente(usuario: CurrentUser, db: DBSession) -> AccesoSesion:
    return rbac_service.consultar_sesion(db, usuario.id)
