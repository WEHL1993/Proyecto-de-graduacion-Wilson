"""Bitácora de auditoría (ADR-15) sin BD: saneamiento, decorador `@auditar`, middleware."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import contexto
from app.core.errors import AppError
from app.core.security import create_access_token
from app.domain.enums import OperacionBitacora
from app.main import app
from app.schemas.auth import LoginRequest, UsuarioAutenticado
from app.services import bitacora_service
from app.services.bitacora_service import auditar, sanear

pytestmark = pytest.mark.bitacora


@pytest.fixture
def capturados(monkeypatch):
    filas: list[dict] = []
    monkeypatch.setattr(bitacora_service, "_insertar", lambda bind, campos: filas.append(campos))
    return filas


class _Sesion(Session):
    def get_bind(self, *args, **kwargs):  # sin motor real
        return object()


def test_sanear_oculta_secretos_y_trunca():
    datos = sanear(
        {
            "password": "ClaveSegura123",
            "token_acceso": "abc",
            "id": uuid.UUID(int=1),
            "monto": Decimal("10.50"),
            "archivo": b"x" * 5000,
            "texto": "a" * 500,
            "lista": list(range(50)),
        }
    )
    assert datos["password"] == "***" and datos["token_acceso"] == "***"
    assert datos["monto"] == "10.50" and datos["archivo"] == "<5000 bytes>"
    assert len(datos["texto"]) == 201
    assert len(datos["lista"]) == 21 and datos["lista"][-1] == "… (+30)"


def test_sanear_modelo_pydantic_no_filtra_password():
    datos = sanear(LoginRequest(email="a@ds.gt", password="ClaveSegura123"))
    assert datos == {"email": "a@ds.gt", "password": "***"}


def test_decorador_registra_exito_con_usuario_y_contexto(capturados):
    usuario = UsuarioAutenticado(id=uuid.uuid4(), roles=[], permisos=[])

    @auditar
    def listar_cosas(db, usuario, filtro):
        return [1, 2]

    token = contexto.establecer(
        contexto.ContextoAuditoria(origen="http", ip="10.0.0.1", metodo="GET", ruta="/x")
    )
    try:
        assert listar_cosas(_Sesion(), usuario, filtro="a") == [1, 2]
    finally:
        contexto.restablecer(token)

    (fila,) = capturados
    assert fila["accion"].endswith("listar_cosas")
    assert fila["operacion"] == OperacionBitacora.LECTURA.value
    assert fila["resultado"] == "exito" and fila["nivel"] == "INFO"
    assert fila["usuario_id"] == usuario.id and fila["ip"] == "10.0.0.1"
    assert fila["origen"] == "servicio" and fila["parametros"] == {
        "usuario": {"id": str(usuario.id), "roles": [], "permisos": []},
        "filtro": "a",
    }


def test_decorador_registra_error_y_relanza(capturados):
    @auditar
    def crear_algo(db):
        raise AppError("YA_EXISTE", "Ya existe.", status_code=409)

    with pytest.raises(AppError):
        crear_algo(_Sesion())

    (fila,) = capturados
    assert fila["operacion"] == "escritura" and fila["resultado"] == "error"
    assert fila["nivel"] == "WARNING" and fila["codigo_error"] == "YA_EXISTE"


def test_un_fallo_al_registrar_no_rompe_la_operacion(monkeypatch):
    def _falla(bind, campos):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(bitacora_service, "_insertar", _falla)

    @auditar
    def crear_algo(db):
        return "ok"

    assert crear_algo(_Sesion()) == "ok"


def test_middleware_registra_peticion_y_devuelve_request_id(monkeypatch):
    registros: list[dict] = []
    monkeypatch.setattr(bitacora_service, "registrar_http", lambda **kw: registros.append(kw))
    usuario = uuid.uuid4()
    token, _ = create_access_token(sub=str(usuario), roles=[], perms=[])

    r = TestClient(app).get("/api/v1/bitacora", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 403 and r.headers["X-Request-ID"]
    (reg,) = registros
    assert reg["metodo"] == "GET" and reg["ruta"] == "/api/v1/bitacora"
    assert reg["status_code"] == 403 and reg["usuario_id"] == usuario


def test_middleware_ignora_health(monkeypatch):
    registros: list[dict] = []
    monkeypatch.setattr(bitacora_service, "registrar_http", lambda **kw: registros.append(kw))
    assert TestClient(app).get("/health").status_code == 200
    assert registros == []
