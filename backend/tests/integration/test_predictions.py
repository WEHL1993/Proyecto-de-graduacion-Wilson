"""Inferencia contra PostgreSQL real: TC-PRED-01/02, registro de modelos y ADR-03.

Requiere la BD migrada; se omiten si no hay conexión. Cada prueba corre en una transacción
que se revierte al final; los artefactos se escriben en un directorio temporal.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.security import create_access_token, hash_password
from app.domain.enums import EstadoModelo
from app.domain.models.auth import Permiso, Rol, Usuario
from app.domain.models.catalog import Categoria, Producto, Ruta
from app.domain.models.ml import MetricaEvaluacion, ModeloML, PronosticoDemanda
from app.domain.models.sales import EtlLote, VentaHistorica
from app.main import app
from app.ml import contracts
from app.ml.inference.cache import limpiar_cache
from app.services import prediction_service, training_service
from tests.ml.conftest import FECHA_FIN, generar_ventas

URL = "/api/v1/predictions/demand"
HP = {"n_estimators": 30, "max_depth": 3, "n_jobs": 1}


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
def entorno(db_session, tmp_path, monkeypatch):
    settings = SimpleNamespace(ml_artifacts_dir=tmp_path, ml_modelo_nombre="demanda_test")
    monkeypatch.setattr(prediction_service, "get_settings", lambda: settings)
    monkeypatch.setattr(training_service, "get_settings", lambda: settings)
    limpiar_cache()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield SimpleNamespace(db=db_session, client=TestClient(app))
    finally:
        app.dependency_overrides.clear()
        limpiar_cache()


def _usuario_consulta(db: Session) -> tuple[dict[str, str], Usuario]:
    permiso = db.scalar(select(Permiso).where(Permiso.codigo == "prediccion:consultar"))
    permiso = permiso or Permiso(codigo="prediccion:consultar", descripcion="consulta")
    rol = Rol(nombre=f"rol-{uuid.uuid4().hex[:8]}", descripcion="prueba", permisos=[permiso])
    usuario = Usuario(
        email=f"pred-{uuid.uuid4().hex[:6]}@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo="Consulta",
        roles=[rol],
    )
    db.add(usuario)
    db.flush()
    token, _ = create_access_token(sub=str(usuario.id), roles=[], perms=["prediccion:consultar"])
    return {"Authorization": f"Bearer {token}"}, usuario


def _sembrar_ventas(db: Session, usuario: Usuario) -> list[uuid.UUID]:
    """Catálogo mínimo + 240 días de ventas sintéticas (2 productos × 2 rutas)."""
    categoria = Categoria(nombre=f"cat-{uuid.uuid4().hex[:6]}")
    db.add(categoria)
    db.flush()
    lote = EtlLote(
        usuario_id=usuario.id, archivo_nombre="pred.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    db.add(lote)
    productos, rutas = {}, {}
    ventas = generar_ventas()
    for sku_id in ventas["producto_id"].unique():
        productos[sku_id] = Producto(
            sku=f"P{sku_id[-6:]}", nombre="Producto", categoria_id=categoria.id
        )
    for ruta_id in ventas["ruta_id"].unique():
        rutas[ruta_id] = Ruta(codigo=f"R{ruta_id[-6:]}", nombre=f"Ruta {ruta_id[-3:]}")
    db.add_all([*productos.values(), *rutas.values()])
    db.flush()
    db.add_all(
        VentaHistorica(
            lote_id=lote.id,
            fecha_venta=v.fecha.date(),
            producto_id=productos[v.producto_id].id,
            ruta_id=rutas[v.ruta_id].id,
            cantidad=Decimal(str(v.cantidad)),
            precio_unitario=Decimal("10.00"),
            monto_total=Decimal(str(v.cantidad)) * 10,
        )
        for v in ventas.itertuples()
    )
    db.flush()
    return [p.id for p in productos.values()]


def test_tc_pred_01_entrenar_promover_y_pronosticar(entorno):
    headers, usuario = _usuario_consulta(entorno.db)
    producto_ids = _sembrar_ventas(entorno.db, usuario)

    modelo = training_service.entrenar_modelo(
        entorno.db, algoritmo="xgboost", hiperparametros=HP, promover=True
    )
    assert modelo.estado == EstadoModelo.PRODUCCION and modelo.promovido_en is not None
    assert modelo.ruta_artefacto == f"models/xgboost/{modelo.version}"
    assert len(modelo.hash_artefacto) == 64
    metricas = entorno.db.scalars(
        select(MetricaEvaluacion).where(MetricaEvaluacion.modelo_id == modelo.id)
    ).all()
    assert {m.tipo_evaluacion for m in metricas} == {"backtest", "holdout"}

    r = entorno.client.post(
        URL,
        json={
            "producto_ids": [str(p) for p in producto_ids],
            "fecha_base": FECHA_FIN.date().isoformat(),
            "horizonte_dias": 7,
            "persistir": True,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["modelo"]["id"] == str(modelo.id)
    for pron in r.json()["pronosticos"]:
        assert len(pron["serie"]) == 7
        assert all(
            p["limite_inferior"] <= p["demanda_predicha"] <= p["limite_superior"]
            for p in pron["serie"]
        )

    filas = entorno.db.scalars(select(PronosticoDemanda)).all()
    assert len(filas) == 14 and all(f.ruta_id is None for f in filas)

    # idempotente: repetir la solicitud no duplica filas
    r2 = entorno.client.post(
        URL,
        json={
            "producto_ids": [str(p) for p in producto_ids],
            "fecha_base": (FECHA_FIN.date()).isoformat(),
            "horizonte_dias": 7,
            "persistir": True,
        },
        headers=headers,
    )
    assert r2.status_code == 200
    total = entorno.db.scalar(select(func.count()).select_from(PronosticoDemanda))
    assert total == 14


def test_tc_pred_02_sin_modelo_productivo_no_persiste(entorno):
    headers, usuario = _usuario_consulta(entorno.db)
    producto_ids = _sembrar_ventas(entorno.db, usuario)
    r = entorno.client.post(
        URL,
        json={"producto_ids": [str(producto_ids[0])], "horizonte_dias": 7, "persistir": True},
        headers=headers,
    )
    assert r.status_code == 400 and r.json()["codigo"] == "SIN_MODELO_PRODUCTIVO"
    assert entorno.db.scalar(select(func.count()).select_from(PronosticoDemanda)) == 0


def test_adr_03_un_solo_modelo_en_produccion(entorno):
    _, usuario = _usuario_consulta(entorno.db)
    _sembrar_ventas(entorno.db, usuario)

    primero = training_service.entrenar_modelo(
        entorno.db, algoritmo="xgboost", hiperparametros=HP, promover=True
    )
    segundo = training_service.entrenar_modelo(
        entorno.db, algoritmo="sklearn", hiperparametros={"n_estimators": 20, "n_jobs": 1}
    )
    assert segundo.estado == EstadoModelo.CANDIDATO and segundo.version != primero.version

    contracts.promover_a_produccion(entorno.db, segundo.id)
    entorno.db.refresh(primero)
    assert primero.estado == EstadoModelo.ARCHIVADO
    assert segundo.estado == EstadoModelo.PRODUCCION
    produccion = entorno.db.scalars(
        select(ModeloML).where(
            ModeloML.nombre == "demanda_test", ModeloML.estado == EstadoModelo.PRODUCCION
        )
    ).all()
    assert [m.id for m in produccion] == [segundo.id]

    # rollback: el índice único parcial impide dos modelos en producción a nivel de BD
    primero.estado = EstadoModelo.PRODUCCION
    primero.promovido_en = segundo.promovido_en + timedelta(seconds=1)
    with pytest.raises(IntegrityError):
        entorno.db.flush()
