"""Métricas de error unificadas (definición única de MAE, RMSE y MAPE).

MAPE: se calcula solo sobre las observaciones con demanda real distinta de cero (la división
por cero no está definida); si no hay ninguna, devuelve `None` (columna `mape` NULL, sección 3.4.2).
"""

from dataclasses import dataclass

import numpy as np

# `metricas_evaluacion.mape` es numeric(7,3): valores mayores desbordarían la columna.
MAPE_MAXIMO = 9999.999


@dataclass(frozen=True)
class Metricas:
    mae: float
    rmse: float
    mape: float | None
    n_muestras: int


def mae(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_real - y_pred)))


def rmse(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_real - y_pred) ** 2)))


def mape(y_real: np.ndarray, y_pred: np.ndarray) -> float | None:
    """MAPE en porcentaje ignorando los puntos con `y_real == 0`; `None` si no queda ninguno."""
    mascara = y_real != 0
    if not mascara.any():
        return None
    relativo = np.abs((y_real[mascara] - y_pred[mascara]) / y_real[mascara])
    return float(np.mean(relativo) * 100)


def calcular_metricas(y_real: object, y_pred: object) -> Metricas:
    real = np.asarray(y_real, dtype=float).ravel()
    pred = np.asarray(y_pred, dtype=float).ravel()
    if real.shape != pred.shape:
        raise ValueError(f"Longitudes distintas: y_real={real.shape}, y_pred={pred.shape}")
    if real.size == 0:
        raise ValueError("No se pueden calcular métricas sin observaciones.")
    return Metricas(
        mae=mae(real, pred), rmse=rmse(real, pred), mape=mape(real, pred), n_muestras=real.size
    )
