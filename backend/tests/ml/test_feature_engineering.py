import numpy as np
import pandas as pd
import pytest

from app.ml.data_preparation.feature_engineering import (
    REZAGOS,
    VENTANAS,
    completar_calendario,
    construir_features,
)
from app.ml.data_preparation.preprocessor import PreprocesadorDemanda
from app.ml.data_preparation.splitters import walk_forward_splits
from app.ml.inference.predictor import PredictorDemanda
from tests.ml.conftest import PRODUCTO_A, RUTA_1


def _serie_lineal(n: int = 60) -> pd.DataFrame:
    fechas = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "fecha": fechas,
            "producto_id": PRODUCTO_A,
            "ruta_id": RUTA_1,
            "cantidad": np.arange(n, dtype=float),
        }
    )


def test_completar_calendario_rellena_dias_sin_venta():
    df = _serie_lineal(5).drop(index=[2])
    completo = completar_calendario(df)
    assert len(completo) == 5
    assert completo.loc[completo["fecha"] == "2025-01-03", "cantidad"].item() == 0.0


def test_rezagos_y_medias_usan_solo_el_pasado():
    f = construir_features(_serie_lineal())
    fila = f.iloc[40]  # y_t = 40
    for k in REZAGOS:
        assert fila[f"lag_{k}"] == 40 - k
    for w in VENTANAS:
        assert fila[f"media_{w}"] == pytest.approx(np.mean(np.arange(40 - w, 40)))
    assert f["media_28"].iloc[:28].isna().all()  # sin historia suficiente


def test_no_hay_fuga_cambiar_y_t_no_altera_features_de_t():
    base = _serie_lineal()
    alterada = base.copy()
    alterada.loc[40, "cantidad"] = 9999.0
    a, b = construir_features(base), construir_features(alterada)
    cols = [c for c in a.columns if c != "cantidad"]
    pd.testing.assert_frame_equal(a.loc[[40], cols], b.loc[[40], cols])
    assert b.loc[41, "lag_1"] == 9999.0  # solo afecta a t+1 en adelante


def test_calendario():
    df = pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2025-03-15", "2025-03-31", "2025-03-03"]),  # sáb, lun, lun
            "producto_id": PRODUCTO_A,
            "ruta_id": RUTA_1,
            "cantidad": 1.0,
        }
    )
    f = construir_features(df).sort_values("fecha")
    # ordenado: 03-03 (lun), 03-15 (sáb), 03-31 (lun)
    assert f["dia_semana"].tolist() == [0, 5, 0]
    assert f["quincena"].tolist() == [1, 1, 2]
    assert f["es_fin_quincena"].tolist() == [0, 1, 1]
    assert f["mes"].unique().tolist() == [3]


def test_features_de_inferencia_coinciden_con_las_de_entrenamiento():
    """`PredictorDemanda._features_paso` debe replicar exactamente `construir_features`."""
    serie = _serie_lineal(60)
    entrenamiento = construir_features(serie).iloc[[-1]]
    prep = PreprocesadorDemanda().ajustar(serie)
    esperado = prep.transformar(entrenamiento).iloc[0]

    predictor = PredictorDemanda(modelo=None, preprocesador=prep)  # type: ignore[arg-type]
    colas = serie["cantidad"].to_numpy()[None, :-1][:, -28:]
    obtenido = predictor._features_paso(
        [(PRODUCTO_A, RUTA_1)], colas, serie["fecha"].iloc[-1]
    ).iloc[0]
    pd.testing.assert_series_equal(obtenido, esperado, check_names=False)


def test_walk_forward_sin_fuga_y_expansivo():
    fechas = pd.Series(pd.date_range("2025-01-01", periods=200, freq="D"))
    folds = list(
        walk_forward_splits(fechas, n_splits=3, test_dias=14, min_train_dias=60, gap_dias=1)
    )
    assert len(folds) == 3
    tamanos = []
    for train, test in folds:
        assert fechas.iloc[train].max() < fechas.iloc[test].min()  # train estrictamente anterior
        assert (fechas.iloc[test].min() - fechas.iloc[train].max()).days == 2  # gap de 1 día
        assert len(test) == 14
        tamanos.append(len(train))
    assert tamanos == sorted(tamanos) and len(set(tamanos)) == 3  # ventana expansiva
    assert fechas.iloc[folds[-1][1]].max() == fechas.max()


def test_walk_forward_omite_folds_si_no_alcanza_el_historico():
    fechas = pd.Series(pd.date_range("2025-01-01", periods=70, freq="D"))
    assert len(list(walk_forward_splits(fechas, n_splits=3, test_dias=14, min_train_dias=60))) == 0
