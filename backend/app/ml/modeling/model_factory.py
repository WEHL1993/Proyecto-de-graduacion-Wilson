"""Interfaz común de entrenamiento/predicción y fábrica por algoritmo (`modelos_ml.algoritmo`)."""

from typing import Any, Protocol

import numpy as np
import pandas as pd

from app.domain.enums import Algoritmo
from app.ml.modeling.sklearn_models import ModeloRandomForest
from app.ml.modeling.xgboost_models import ModeloXGBoost


class ModeloDemanda(Protocol):
    algoritmo: str
    hiperparametros: dict[str, Any]

    def entrenar(self, X: pd.DataFrame, y: np.ndarray) -> "ModeloDemanda": ...

    def predecir(self, X: pd.DataFrame) -> np.ndarray: ...


_CONSTRUCTORES: dict[str, type[ModeloRandomForest] | type[ModeloXGBoost]] = {
    Algoritmo.SKLEARN.value: ModeloRandomForest,
    Algoritmo.XGBOOST.value: ModeloXGBoost,
}


def crear_modelo(algoritmo: str, **hiperparametros: Any) -> ModeloDemanda:
    try:
        constructor = _CONSTRUCTORES[str(algoritmo)]
    except KeyError:
        disponibles = ", ".join(sorted(_CONSTRUCTORES))
        raise ValueError(
            f"Algoritmo no soportado: {algoritmo!r} (disponibles: {disponibles})"
        ) from None
    return constructor(**hiperparametros)
