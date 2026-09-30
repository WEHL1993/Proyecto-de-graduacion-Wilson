"""Entrenamiento, artefactos, integridad SHA-256, reproducibilidad e intervalos."""

import json
import shutil

import pandas as pd
import pytest

from app.ml import contracts
from app.ml.inference.cache import limpiar_cache, obtener_predictor
from app.ml.pipeline import entrenar_y_evaluar
from app.ml.registry import artifact_store
from tests.ml.conftest import FECHA_FIN, PRODUCTO_A, PRODUCTO_B

HP = {
    "xgboost": {"n_estimators": 40, "max_depth": 3, "n_jobs": 1},
    "sklearn": {"n_estimators": 30, "max_depth": 6, "n_jobs": 1},
}


@pytest.fixture(scope="module", params=["xgboost", "sklearn"])
def entrenado(request, ventas):
    return request.param, entrenar_y_evaluar(ventas, request.param, HP[request.param])


def test_metricas_backtest_y_holdout(entrenado):
    _, res = entrenado
    tipos = {(m.tipo_evaluacion.value, m.producto_id) for m in res.metricas}
    assert ("backtest", None) in tipos and ("holdout", None) in tipos
    assert ("holdout", PRODUCTO_A) in tipos and ("holdout", PRODUCTO_B) in tipos
    for m in res.metricas:
        assert m.metricas.mae >= 0 and m.metricas.rmse >= m.metricas.mae - 1e-9
        assert m.periodo_desde <= m.periodo_hasta
    # patrón semanal fuerte y poco ruido: el modelo debe ser útil
    bt = next(m for m in res.metricas if m.tipo_evaluacion.value == "backtest")
    assert bt.metricas.mape is not None and bt.metricas.mape < 25
    assert res.informe["cobertura_intervalo_holdout"] > 0.6


def test_artefactos_hash_y_carga(entrenado, tmp_path):
    algoritmo, res = entrenado
    guardado = artifact_store.guardar_artefactos(
        tmp_path,
        algoritmo=algoritmo,
        version="v1.0.1",
        modelo=res.modelo,
        preprocesador=res.preprocesador,
        informe=res.informe,
    )
    carpeta = tmp_path / "models" / algoritmo / "v1.0.1"
    assert guardado.ruta_relativa == f"models/{algoritmo}/v1.0.1"
    for nombre in ("model.bin", "preprocessor.bin", "feature_schema.json", "training_report.json"):
        assert (carpeta / nombre).is_file()
    assert guardado.hash_modelo == artifact_store.calcular_sha256(carpeta / "model.bin")
    assert len(guardado.hash_modelo) == 64
    esquema = json.loads((carpeta / "feature_schema.json").read_text())
    assert esquema == guardado.esquema_features

    modelo, prep = artifact_store.cargar_artefactos(
        tmp_path, guardado.ruta_relativa, guardado.hash_modelo, guardado.esquema_features
    )
    assert prep.features == res.preprocesador.features
    with pytest.raises(FileExistsError):  # las versiones son inmutables
        artifact_store.guardar_artefactos(
            tmp_path,
            algoritmo=algoritmo,
            version="v1.0.1",
            modelo=res.modelo,
            preprocesador=res.preprocesador,
            informe={},
        )


def test_hash_alterado_se_rechaza_antes_de_deserializar(entrenado, tmp_path):
    algoritmo, res = entrenado
    g = artifact_store.guardar_artefactos(
        tmp_path,
        algoritmo=algoritmo,
        version="v1.0.2",
        modelo=res.modelo,
        preprocesador=res.preprocesador,
        informe={},
    )
    with pytest.raises(contracts.ArtefactoCorrupto):  # hash distinto al registrado
        artifact_store.cargar_artefactos(tmp_path, g.ruta_relativa, "0" * 64, g.esquema_features)
    (tmp_path / g.ruta_relativa / "model.bin").write_bytes(b"manipulado")
    with pytest.raises(contracts.ArtefactoCorrupto):
        artifact_store.cargar_artefactos(
            tmp_path, g.ruta_relativa, g.hash_modelo, g.esquema_features
        )
    shutil.rmtree(tmp_path / g.ruta_relativa)
    with pytest.raises(contracts.ArtefactoNoEncontrado):
        artifact_store.cargar_artefactos(
            tmp_path, g.ruta_relativa, g.hash_modelo, g.esquema_features
        )


def test_ruta_fuera_de_ml_artifacts_se_rechaza(tmp_path):
    with pytest.raises(contracts.ArtefactoCorrupto):
        artifact_store.cargar_artefactos(tmp_path, "../../etc", "0" * 64, {})


def test_prediccion_reproducible_e_intervalo_coherente(entrenado, ventas, tmp_path):
    algoritmo, res = entrenado
    g = artifact_store.guardar_artefactos(
        tmp_path,
        algoritmo=algoritmo,
        version="v1.0.3",
        modelo=res.modelo,
        preprocesador=res.preprocesador,
        informe={},
    )
    limpiar_cache()
    import uuid

    kwargs = dict(
        modelo_id=uuid.uuid4(),
        raiz=tmp_path,
        ruta_relativa=g.ruta_relativa,
        hash_artefacto=g.hash_modelo,
        esquema_features=g.esquema_features,
    )
    predictor = obtener_predictor(**kwargs)
    assert obtener_predictor(**kwargs) is predictor  # caché

    historial = ventas[ventas["producto_id"] == PRODUCTO_A]
    a = predictor.predecir(historial, FECHA_FIN.date(), 7)
    b = predictor.predecir(historial, FECHA_FIN.date(), 7)
    assert a == b
    # 2 rutas × 7 días
    assert len(a) == 14 and {p.horizonte_dias for p in a} == set(range(1, 8))
    for p in a:
        assert 0 <= p.inferior <= p.demanda <= p.superior
        assert p.fecha_objetivo > FECHA_FIN.date()
    limpiar_cache()


def test_historial_insuficiente(entrenado):
    _, res = entrenado
    from app.ml.inference.predictor import PredictorDemanda

    corto = pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2025-12-30", "2025-12-31"]),
            "producto_id": PRODUCTO_A,
            "ruta_id": "r",
            "cantidad": [1.0, 2.0],
        }
    )
    with pytest.raises(contracts.HistorialInsuficiente):
        PredictorDemanda(res.modelo, res.preprocesador).predecir(corto, FECHA_FIN.date(), 3)


def test_datos_insuficientes_para_entrenar(ventas):
    corto = ventas[ventas["fecha"] >= ventas["fecha"].max() - pd.Timedelta(days=40)]
    with pytest.raises(contracts.DatosInsuficientes):
        entrenar_y_evaluar(corto, "xgboost", HP["xgboost"])
