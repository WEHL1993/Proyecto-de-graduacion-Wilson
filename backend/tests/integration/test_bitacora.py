"""Bitácora de auditoría (ADR-15) contra PostgreSQL: registro por caso de uso, consulta RBAC e
inmutabilidad (trigger)."""

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.domain.models.bitacora import Bitacora
from app.services import bitacora_service
from tests.integration.conftest import crear_usuario, encabezados

pytestmark = pytest.mark.bitacora


@pytest.fixture(autouse=True)
def _bitacora_en_la_transaccion(db_tx, monkeypatch):
    """El middleware escribe con el motor global: lo redirige a la transacción de la prueba."""
    monkeypatch.setattr(bitacora_service, "get_engine", lambda: db_tx.get_bind())


# TC-AUD-01
def test_cada_caso_de_uso_deja_registro_con_usuario_y_request_id(cliente, db_tx):
    admin = crear_usuario(db_tx, "auditor")
    h = encabezados(admin, "usuarios:gestionar", "bitacora:leer")

    r = cliente.get("/api/v1/users", headers=h)
    assert r.status_code == 200
    request_id = r.headers["X-Request-ID"]

    r = cliente.get("/api/v1/bitacora", params={"request_id": request_id}, headers=h)
    assert r.status_code == 200
    por_origen = {x["origen"]: x for x in r.json()["registros"]}
    assert por_origen["http"]["accion"] == "GET /api/v1/users"
    assert por_origen["servicio"]["accion"].endswith("user_service.listar")
    assert por_origen["servicio"]["usuario_id"] == str(admin.id)
    assert por_origen["servicio"]["parametros"]["limit"] == 50


# TC-AUD-02
def test_login_fallido_queda_registrado_sin_la_contrasena(cliente, db_tx):
    r = cliente.post(
        "/api/v1/auth/login", json={"email": "nadie@ds.gt", "password": "ClaveSegura123"}
    )
    assert r.status_code == 401
    filas = db_tx.scalars(select(Bitacora).where(Bitacora.accion.like("%auth_service.login"))).all()
    assert filas and filas[-1].resultado == "error"
    assert filas[-1].codigo_error and "ClaveSegura123" not in str(filas[-1].parametros)
    assert filas[-1].parametros["datos"]["password"] == "***"


# TC-AUD-03
def test_consultar_bitacora_exige_permiso(cliente, db_tx):
    usuario = crear_usuario(db_tx, "sin_permiso")
    r = cliente.get("/api/v1/bitacora", headers=encabezados(usuario, "inventario:leer"))
    assert r.status_code == 403 and r.json()["codigo"] == "PERMISO_DENEGADO"
    assert cliente.get("/api/v1/bitacora").status_code == 401


# TC-AUD-04
def test_la_bitacora_es_inmutable(db_tx):
    db_tx.add(
        Bitacora(
            nivel="INFO", origen="servicio", operacion="lectura", accion="x", resultado="exito"
        )
    )
    db_tx.flush()
    for sentencia in (
        update(Bitacora).values(accion="alterada"),
        delete(Bitacora),
    ):
        with pytest.raises(DBAPIError, match="solo inserción"):
            with db_tx.begin_nested():
                db_tx.execute(sentencia)
    with pytest.raises(DBAPIError, match="solo inserción"):
        with db_tx.begin_nested():
            db_tx.execute(text("TRUNCATE bitacora"))
