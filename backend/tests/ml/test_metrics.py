import numpy as np
import pytest

from app.ml.evaluation.metrics import calcular_metricas


def test_metricas_basicas():
    m = calcular_metricas([10, 20, 30], [12, 18, 33])
    assert m.mae == pytest.approx((2 + 2 + 3) / 3)
    assert m.rmse == pytest.approx(np.sqrt((4 + 4 + 9) / 3))
    assert m.mape == pytest.approx((0.2 + 0.1 + 0.1) / 3 * 100)
    assert m.n_muestras == 3


def test_mape_ignora_ceros_sin_dividir():
    m = calcular_metricas([0, 10], [5, 12])
    assert m.mape == pytest.approx(20.0)  # solo cuenta el punto con real != 0
    assert m.mae == pytest.approx((5 + 2) / 2)


def test_mape_none_si_toda_la_demanda_real_es_cero():
    m = calcular_metricas([0, 0, 0], [1, 2, 3])
    assert m.mape is None
    assert m.mae == pytest.approx(2.0)


def test_valida_entradas():
    with pytest.raises(ValueError):
        calcular_metricas([1, 2], [1])
    with pytest.raises(ValueError):
        calcular_metricas([], [])
