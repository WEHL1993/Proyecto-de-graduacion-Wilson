"""XGBoost Regressor para demanda diaria con covariables tabulares (rezagos + calendario).

Se usa el método `hist` (rápido en CPU) con submuestreo de filas/columnas y regularización L2
para reducir el sobreajuste en series cortas y ruidosas. Las predicciones se acotan en 0.
"""

from typing import Any, Self

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.domain.enums import Algoritmo

HIPERPARAMETROS_POR_DEFECTO: dict[str, Any] = {
    "n_estimators": 400,
    "learning_rate": 0.05,
    "max_depth": 5,
    "min_child_weight": 3,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "n_jobs": -1,
    "random_state": 42,
}


class ModeloXGBoost:
    algoritmo = Algoritmo.XGBOOST.value

    def __init__(self, **hiperparametros: Any) -> None:
        self.hiperparametros = {**HIPERPARAMETROS_POR_DEFECTO, **hiperparametros}
        self._estimador = XGBRegressor(**self.hiperparametros)

    def entrenar(self, X: pd.DataFrame, y: np.ndarray, pesos: np.ndarray | None = None) -> Self:
        self._estimador.fit(X, y, sample_weight=pesos)
        return self

    def predecir(self, X: pd.DataFrame) -> np.ndarray:
        return np.clip(self._estimador.predict(X), 0.0, None)
