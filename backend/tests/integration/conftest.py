"""Fixtures compartidas de las pruebas de integración de la fase 8 (usuarios, reportes, alertas).

Requieren la BD migrada; se omiten si no hay conexión. Cada prueba corre en una transacción que
se revierte al final (los `commit` de los servicios liberan un SAVEPOINT).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.security import create_access_token, hash_password
from app.domain.models.auth import Usuario
from app.main import app


@pytest.fixture
def db_tx():
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
def cliente(db_tx):
    app.dependency_overrides[get_db] = lambda: db_tx
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def crear_usuario(db: Session, nombre: str, **extra) -> Usuario:
    usuario = Usuario(
        email=f"{nombre}-{uuid.uuid4().hex[:8]}@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo=nombre,
        **extra,
    )
    db.add(usuario)
    db.flush()
    return usuario


def encabezados(usuario: Usuario, *permisos: str, roles: tuple[str, ...] = ()) -> dict[str, str]:
    token, _ = create_access_token(sub=str(usuario.id), roles=list(roles), perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}
