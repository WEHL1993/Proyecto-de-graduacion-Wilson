"""Preprocesador serializable (`preprocessor.bin`): fija el orden de las features y el
código numérico de cada serie (producto, ruta), garantizando el mismo esquema en inferencia."""

from dataclasses import dataclass, field

import pandas as pd

from app.ml.data_preparation.feature_engineering import (
    COL_SERIE,
    FEATURES_CALENDARIO,
    FEATURES_REZAGO,
)

FEATURES = ["serie_codigo", *FEATURES_REZAGO, *FEATURES_CALENDARIO]
SERIE_DESCONOCIDA = -1


def clave_serie(producto_id: object, ruta_id: object) -> str:
    return f"{producto_id}|{ruta_id}"


@dataclass
class PreprocesadorDemanda:
    codigos_serie: dict[str, int] = field(default_factory=dict)
    features: list[str] = field(default_factory=lambda: list(FEATURES))
    # Cuantiles (2,5 % y 97,5 %) de los residuos fuera de muestra: calibran el intervalo al 95 %.
    residuo_q_inferior: float = 0.0
    residuo_q_superior: float = 0.0

    def ajustar(self, df: pd.DataFrame) -> "PreprocesadorDemanda":
        claves = sorted({clave_serie(p, r) for p, r in df[COL_SERIE].itertuples(index=False)})
        self.codigos_serie = {clave: i for i, clave in enumerate(claves)}
        return self

    def transformar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Devuelve solo las columnas de `features`, en orden. No elimina filas con NaN."""
        claves = [clave_serie(p, r) for p, r in df[COL_SERIE].itertuples(index=False)]
        salida = df.copy()
        salida["serie_codigo"] = [self.codigos_serie.get(c, SERIE_DESCONOCIDA) for c in claves]
        return salida[self.features]
