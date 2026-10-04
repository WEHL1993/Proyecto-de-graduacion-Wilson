"""Pruebas de integración de `POST /auth/login` contra PostgreSQL real (TC-AUTH-01, TC-AUTH-02).

Requiere la BD migrada (`make migrate`); se omiten si no hay conexión. Cada prueba corre
dentro de una transacción (con SAVEPOINT para los `commit()` del servicio) que se
revierte al final, igual que `tests/integration/test_schema_constraints.py`.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.security import hash_password
from app.domain.models.auth import Permiso, Rol, Usuario
from app.main import app

ROL_PRUEBA = "Ventas (prueba login)"


@pytest.fixture
def db_session():
    try:
        connection = get_engine().connect()
    except (OperationalError, UnicodeDecodeError):  # psycopg2 en Windows
        pytest.skip("PostgreSQL no disponible")
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def usuario_ventas(db_session):
    # La BD de pruebas puede traer el seed RBAC: se reutiliza el permiso y se usa un rol propio.
    permiso = db_session.scalar(select(Permiso).where(Permiso.codigo == "carga_ruta:generar"))
    if permiso is None:
        permiso = Permiso(codigo="carga_ruta:generar", descripcion="Generar cargas de ruta")
    rol = Rol(nombre=ROL_PRUEBA, descripcion="Rol de ventas de prueba", permisos=[permiso])
    usuario = Usuario(
        email="ventas@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo="Vendedor de Prueba",
        roles=[rol],
    )
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_login_credenciales_validas_devuelve_token_roles_y_permisos(client, usuario_ventas):
    """TC-AUTH-01."""
    respuesta = client.post(
        "/api/v1/auth/login", json={"email": "ventas@ds.gt", "password": "ClaveSegura123"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["access_token"]
    assert cuerpo["usuario"]["roles"] == [ROL_PRUEBA]
    assert cuerpo["usuario"]["permisos"] == ["carga_ruta:generar"]


def test_login_password_incorrecta_devuelve_401_generico(client, usuario_ventas):
    """TC-AUTH-02 (mitad 1: contraseña errónea)."""
    respuesta = client.post(
        "/api/v1/auth/login", json={"email": "ventas@ds.gt", "password": "clave-erronea"}
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "CREDENCIALES_INVALIDAS"


def test_login_correo_inexistente_devuelve_el_mismo_401_generico(client, usuario_ventas):
    """TC-AUTH-02 (mitad 2): mensaje idéntico al de contraseña incorrecta."""
    respuesta_inexistente = client.post(
        "/api/v1/auth/login", json={"email": "no-existe@ds.gt", "password": "cualquier-clave"}
    )
    respuesta_password_erronea = client.post(
        "/api/v1/auth/login", json={"email": "ventas@ds.gt", "password": "clave-erronea"}
    )
    assert respuesta_inexistente.status_code == 401
    assert respuesta_inexistente.json() == respuesta_password_erronea.json()


def test_login_usuario_inactivo_devuelve_401_generico(client, db_session):
    usuario = Usuario(
        email="inactivo@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo="Usuario Inactivo",
        activo=False,
    )
    db_session.add(usuario)
    db_session.commit()

    respuesta = client.post(
        "/api/v1/auth/login", json={"email": "inactivo@ds.gt", "password": "ClaveSegura123"}
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "CREDENCIALES_INVALIDAS"
