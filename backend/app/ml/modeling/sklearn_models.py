"""Baseline scikit-learn: RandomForestRegressor."""

from typing import Any, Self

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from app.domain.enums import Algoritmo

HIPERPARAMETROS_POR_DEFECTO: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": 12,
    "min_samples_leaf": 3,
    "max_features": 0.7,
    "n_jobs": -1,
    "random_state": 42,
}


class ModeloRandomForest:
    algoritmo = Algoritmo.SKLEARN.value

    def __init__(self, **hiperparametros: Any) -> None:
        self.hiperparametros = {**HIPERPARAMETROS_POR_DEFECTO, **hiperparametros}
        self._estimador = RandomForestRegressor(**self.hiperparametros)

    def entrenar(self, X: pd.DataFrame, y: np.ndarray) -> Self:
        self._estimador.fit(X, y)
        return self

    def predecir(self, X: pd.DataFrame) -> np.ndarray:
        return np.clip(self._estimador.predict(X), 0.0, None)
