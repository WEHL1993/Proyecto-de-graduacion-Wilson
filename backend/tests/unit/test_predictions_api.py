"""TC-PRED-01/02/03 sin BD: los repositorios se sustituyen por dobles en memoria.

Los artefactos son reales (modelo entrenado y guardado en un directorio temporal), de modo que
se ejercita el camino completo: caché + hash SHA-256 → predictor recursivo → agregación → DTO.
"""

import uuid
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.ml.inference.cache import limpiar_cache
from app.ml.pipeline import entrenar_y_evaluar
from app.ml.registry import artifact_store
from app.services import prediction_service
from tests.ml.conftest import FECHA_FIN, PRODUCTO_A, PRODUCTO_B, RUTA_1, generar_ventas

URL = "/api/v1/predictions/demand"
PRODUCTOS = [uuid.UUID(PRODUCTO_A), uuid.UUID(PRODUCTO_B)]


def _headers(*permisos: str) -> dict[str, str]:
    token, _ = create_access_token(sub=str(uuid.uuid4()), roles=[], perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def modelo_publicado(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("ml_artifacts")
    ventas = generar_ventas()
    res = entrenar_y_evaluar(ventas, "xgboost", {"n_estimators": 30, "max_depth": 3, "n_jobs": 1})
    g = artifact_store.guardar_artefactos(
        raiz,
        algoritmo="xgboost",
        version="v1.0.1",
        modelo=res.modelo,
        preprocesador=res.preprocesador,
        informe={},
    )
    fila = SimpleNamespace(
        id=uuid.uuid4(),
        nombre="demanda_diaria",
        algoritmo="xgboost",
        version="v1.0.1",
        ruta_artefacto=g.ruta_relativa,
        hash_artefacto=g.hash_modelo,
        esquema_features=g.esquema_features,
    )
    filas_ventas = [
        (f.fecha.date(), uuid.UUID(f.producto_id), uuid.UUID(f.ruta_id), f.cantidad)
        for f in ventas.itertuples()
    ]
    return SimpleNamespace(raiz=raiz, fila=fila, ventas=filas_ventas)


@pytest.fixture
def entorno(monkeypatch, modelo_publicado):
    """Cliente con doble de repositorios; `persistidos` recoge los upserts de pronósticos."""
    limpiar_cache()
    persistidos: list[dict] = []
    estado = SimpleNamespace(modelo=modelo_publicado.fila, raiz=modelo_publicado.raiz)

    monkeypatch.setattr(
        prediction_service,
        "get_settings",
        lambda: SimpleNamespace(ml_artifacts_dir=estado.raiz, ml_modelo_nombre="demanda_diaria"),
    )
    srv = prediction_service
    monkeypatch.setattr(srv.model_repo, "obtener_produccion", lambda db, nombre: estado.modelo)
    monkeypatch.setattr(
        srv.catalog_repo, "productos_existentes", lambda db, ids: set(ids) & set(PRODUCTOS)
    )
    monkeypatch.setattr(srv.catalog_repo, "ruta_existe", lambda db, ruta_id: True)

    def _ventas(db, *, hasta=None, producto_ids=None, ruta_id=None):
        return [
            v
            for v in modelo_publicado.ventas
            if (hasta is None or v[0] <= hasta)
            and (producto_ids is None or v[1] in producto_ids)
            and (ruta_id is None or str(v[2]) == str(ruta_id))
        ]

    monkeypatch.setattr(srv.sales_repo, "ventas_diarias", _ventas)
    monkeypatch.setattr(
        srv.forecast_repo,
        "upsert_pronosticos",
        lambda db, filas: persistidos.extend(filas) or len(filas),
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        yield SimpleNamespace(client=TestClient(app), persistidos=persistidos, estado=estado)
    finally:
        app.dependency_overrides.clear()
        limpiar_cache()


def _cuerpo(**extra) -> dict:
    return {
        "producto_ids": [str(p) for p in PRODUCTOS],
        "fecha_base": FECHA_FIN.date().isoformat(),
        "horizonte_dias": 7,
        **extra,
    }


# ------------------------------------------------------------------ TC-PRED-01
def test_tc_pred_01_pronostico_7_dias_con_intervalo_y_persistencia(entorno, modelo_publicado):
    r = entorno.client.post(
        URL, json=_cuerpo(persistir=True), headers=_headers("prediccion:consultar")
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["modelo"] == {
        "id": str(modelo_publicado.fila.id),
        "algoritmo": "xgboost",
        "version": "v1.0.1",
    }
    datetime.fromisoformat(cuerpo["generado_en"])
    assert {p["producto_id"] for p in cuerpo["pronosticos"]} == {str(p) for p in PRODUCTOS}
    esperadas = [FECHA_FIN.date() + timedelta(days=i) for i in range(1, 8)]
    for pron in cuerpo["pronosticos"]:
        assert [date.fromisoformat(p["fecha_objetivo"]) for p in pron["serie"]] == esperadas
        for p in pron["serie"]:
            assert p["limite_inferior"] <= p["demanda_predicha"] <= p["limite_superior"]
    # filas guardadas en pronosticos_demanda: 2 productos × 7 días, ruta agregada = NULL
    assert len(entorno.persistidos) == 14
    assert {f["ruta_id"] for f in entorno.persistidos} == {None}
    assert {f["horizonte_dias"] for f in entorno.persistidos} == set(range(1, 8))
    assert all(f["modelo_id"] == modelo_publicado.fila.id for f in entorno.persistidos)
    assert all(
        f["limite_inferior"] <= f["demanda_predicha"] <= f["limite_superior"]
        for f in entorno.persistidos
    )


def test_sin_persistir_no_guarda_y_sin_intervalo_omite_limites(entorno):
    r = entorno.client.post(
        URL, json=_cuerpo(incluir_intervalo=False), headers=_headers("prediccion:consultar")
    )
    assert r.status_code == 200
    punto = r.json()["pronosticos"][0]["serie"][0]
    assert "limite_inferior" not in punto and "limite_superior" not in punto
    assert entorno.persistidos == []


def test_pronostico_por_ruta_persiste_ruta_id(entorno):
    r = entorno.client.post(
        URL, json=_cuerpo(ruta_id=RUTA_1, persistir=True), headers=_headers("prediccion:consultar")
    )
    assert r.status_code == 200, r.text
    assert {str(f["ruta_id"]) for f in entorno.persistidos} == {RUTA_1}


def test_producto_inexistente_o_sin_historial(entorno):
    h = _headers("prediccion:consultar")
    r = entorno.client.post(URL, json=_cuerpo(producto_ids=[str(uuid.uuid4())]), headers=h)
    assert (r.status_code, r.json()["codigo"]) == (400, "PRODUCTO_NO_ENCONTRADO")

    # fecha_base anterior a las ventas: catálogo válido pero sin historial
    r = entorno.client.post(URL, json=_cuerpo(fecha_base="2020-01-01"), headers=h)
    assert (r.status_code, r.json()["codigo"]) == (400, "HISTORIAL_INSUFICIENTE")


def test_artefacto_manipulado_devuelve_500_corrupto(entorno):
    """TC-ML-06: hash alterado → 500 ARTEFACTO_CORRUPTO; no se sirve predicción."""
    actual = entorno.estado.modelo
    entorno.estado.modelo = SimpleNamespace(**{**vars(actual), "hash_artefacto": "0" * 64})
    r = entorno.client.post(URL, json=_cuerpo(), headers=_headers("prediccion:consultar"))
    assert (r.status_code, r.json()["codigo"]) == (500, "ARTEFACTO_CORRUPTO")


# ------------------------------------------------------------------ TC-PRED-02
def test_tc_pred_02_sin_modelo_productivo(entorno):
    entorno.estado.modelo = None
    r = entorno.client.post(
        URL, json=_cuerpo(persistir=True), headers=_headers("prediccion:consultar")
    )
    assert r.status_code == 400
    assert r.json()["codigo"] == "SIN_MODELO_PRODUCTIVO"
    assert entorno.persistidos == []  # ningún pronóstico persistido


# ------------------------------------------------------------------ TC-PRED-03
@pytest.mark.parametrize("horizonte", [45, 0, -1])
def test_tc_pred_03_horizonte_fuera_de_rango_es_422(entorno, horizonte):
    r = entorno.client.post(
        URL,
        json=_cuerpo(horizonte_dias=horizonte, persistir=True),
        headers=_headers("prediccion:consultar"),
    )
    assert r.status_code == 422
    assert any("horizonte_dias" in e["loc"] for e in r.json()["detail"])
    assert entorno.persistidos == []


def test_lista_de_productos_vacia_es_422(entorno):
    r = entorno.client.post(
        URL, json=_cuerpo(producto_ids=[]), headers=_headers("prediccion:consultar")
    )
    assert r.status_code == 422


# ------------------------------------------------------------------ RBAC
def test_sin_token_401_y_sin_permiso_403(entorno):
    assert entorno.client.post(URL, json=_cuerpo()).status_code == 401
    r = entorno.client.post(URL, json=_cuerpo(), headers=_headers("etl:cargar"))
    assert r.status_code == 403
