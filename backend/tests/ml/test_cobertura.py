"""Entrenamiento con huecos de cobertura y demanda censurada (ADR-14, sin BD)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.ml.contracts import HistorialInsuficiente
from app.ml.data_preparation.feature_engineering import (
    REZAGOS,
    completar_calendario,
    construir_features,
)
from app.ml.pipeline import PESO_OBSERVACION_CENSURADA, entrenar_y_evaluar
from tests.ml.conftest import PRODUCTO_A, RUTA_1, RUTA_2

HP = {"n_estimators": 30, "max_depth": 3, "n_jobs": 1}


def _serie(inicio: str, dias: int, ruta: str = RUTA_1, base: float = 30.0) -> pd.DataFrame:
    fechas = pd.date_range(inicio, periods=dias, freq="D")
    cantidad = base + 10 * (fechas.dayofweek >= 4) + np.arange(dias) % 3
    return pd.DataFrame(
        {"fecha": fechas, "producto_id": PRODUCTO_A, "ruta_id": ruta, "cantidad": cantidad}
    )


def _ventas_con_hueco(dias_base: int = 90, dias_liquidados: int = 60) -> pd.DataFrame:
    """Base Excel (ene-mar 2025) y liquidaciones un año después: hueco sin información."""
    return pd.concat(
        [_serie("2025-01-01", dias_base), _serie("2026-03-01", dias_liquidados)],
        ignore_index=True,
    )


def _cobertura(dias_base: int = 90, dias_liquidados: int = 60) -> dict[str, list]:
    base_fin = (pd.Timestamp("2025-01-01") + pd.Timedelta(days=dias_base - 1)).date()
    liq_fin = (pd.Timestamp("2026-03-01") + pd.Timedelta(days=dias_liquidados - 1)).date()
    return {RUTA_1: [(date(2025, 1, 1), base_fin), (date(2026, 3, 1), liq_fin)]}


def test_sin_cobertura_el_hueco_se_rellena_con_ceros_como_siempre():
    completo = completar_calendario(_ventas_con_hueco())
    assert len(completo) == (pd.Timestamp("2026-04-29") - pd.Timestamp("2025-01-01")).days + 1
    assert "segmento" not in completo.columns


def test_con_cobertura_el_hueco_no_se_rellena_y_marca_segmentos():
    completo = completar_calendario(_ventas_con_hueco(), cobertura=_cobertura())
    assert len(completo) == 90 + 60
    assert sorted(completo["segmento"].unique()) == [1, 2]
    assert completo.loc[completo["fecha"] == "2026-03-01", "segmento"].item() == 2


def test_dia_sin_fila_dentro_del_rango_cubierto_es_cero():
    ventas = _ventas_con_hueco().drop(index=[100])  # un día del tramo liquidado sin ventas
    completo = completar_calendario(ventas, cobertura=_cobertura())
    assert len(completo) == 150
    dia = pd.Timestamp("2026-03-01") + pd.Timedelta(days=10)
    assert completo.loc[completo["fecha"] == dia, "cantidad"].item() == 0.0


def test_los_rezagos_no_cruzan_el_hueco():
    completo = completar_calendario(_ventas_con_hueco(), cobertura=_cobertura())
    f = construir_features(completo)
    segundo = f[f["segmento"] == 2].sort_values("fecha")
    # Los primeros 28 días del tramo liquidado no tienen historia propia: NaN, no valores de 2025.
    assert segundo["media_28"].iloc[:28].isna().all()
    assert not np.isnan(segundo["media_28"].iloc[28])
    fila = segundo.iloc[40]
    for k in REZAGOS:
        assert fila[f"lag_{k}"] == segundo["cantidad"].iloc[40 - k]


def test_la_censura_se_propaga_y_los_dias_rellenados_no_son_censurados():
    ventas = _ventas_con_hueco().assign(censurada=0.0)
    ventas.loc[ventas["fecha"] == "2026-03-05", "censurada"] = 1.0
    completo = completar_calendario(ventas, cobertura=_cobertura())
    assert completo.loc[completo["fecha"] == "2026-03-05", "censurada"].item() == 1.0
    assert completo["censurada"].sum() == 1.0


def test_entrenamiento_con_cobertura_usa_ambos_tramos_y_pesa_la_censura():
    ventas = _ventas_con_hueco(dias_base=120, dias_liquidados=60).assign(censurada=0.0)
    ventas.loc[ventas["fecha"].between("2026-04-10", "2026-04-14"), "censurada"] = 1.0
    res = entrenar_y_evaluar(
        ventas, "xgboost", HP, cobertura=_cobertura(dias_base=120, dias_liquidados=60)
    )
    assert res.informe["con_cobertura"] is True
    assert res.informe["n_observaciones_censuradas"] == 5
    assert res.informe["peso_observacion_censurada"] == PESO_OBSERVACION_CENSURADA
    # Filas con historia: 92 del tramo base (120-28) + 32 del liquidado (60-28).
    assert res.informe["n_filas_entrenamiento"] == (120 - 28) + (60 - 28)
    tipos = {(m.tipo_evaluacion.value, m.producto_id) for m in res.metricas}
    assert ("backtest", None) in tipos and ("holdout", None) in tipos


def test_ultimo_tramo_corto_se_reporta_como_historial_insuficiente():
    ventas = _ventas_con_hueco(dias_base=120, dias_liquidados=30)
    with pytest.raises(HistorialInsuficiente):
        entrenar_y_evaluar(
            ventas, "xgboost", HP, cobertura=_cobertura(dias_base=120, dias_liquidados=30)
        )


def test_series_inactivas_al_corte_se_omiten_sin_fallar():
    """Una ruta sin liquidaciones recientes no impide entrenar con las rutas liquidadas."""
    base = pd.concat(
        [_serie("2025-01-01", 120, RUTA_1), _serie("2025-01-01", 120, RUTA_2, base=15.0)],
        ignore_index=True,
    )
    liquidado = _serie("2026-03-01", 60, RUTA_1)
    ventas = pd.concat([base, liquidado], ignore_index=True)
    cobertura = {
        RUTA_1: [(date(2025, 1, 1), date(2025, 4, 30)), (date(2026, 3, 1), date(2026, 4, 29))],
        RUTA_2: [(date(2025, 1, 1), date(2025, 4, 30))],
    }
    res = entrenar_y_evaluar(ventas, "xgboost", HP, cobertura=cobertura)
    assert res.informe["n_series"] == 2
    assert res.ventana_hasta == date(2026, 4, 29)
