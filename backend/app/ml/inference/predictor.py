"""Pronóstico recursivo multi-paso con intervalo al 95 % (cuantiles empíricos de residuos).

El modelo es de 1 paso: para el día `t+h` se calculan rezagos/medias con el historial real y
las predicciones ya emitidas para `t+1..t+h-1`. Las características se derivan con las mismas
definiciones de `feature_engineering` (verificado en `tests/ml`).

Intervalo: `[ŷ + q_inf·f(h), ŷ + q_sup·f(h)]` acotado a `[0, ∞)`, con `q_*` los cuantiles 2,5 %
y 97,5 % de los residuos fuera de muestra (walk-forward) y `f(h) = sqrt(1 + 0.15·(h-1))`, que
ensancha el intervalo a medida que crece el error acumulado del pronóstico recursivo.
"""

from datetime import date

import numpy as np
import pandas as pd

from app.ml.contracts import HistorialInsuficiente, PuntoPronostico
from app.ml.data_preparation.feature_engineering import (
    COL_SERIE,
    HISTORIA_MINIMA_DIAS,
    REZAGOS,
    VENTANAS,
    agregar_calendario,
    completar_calendario,
)
from app.ml.data_preparation.preprocessor import PreprocesadorDemanda
from app.ml.modeling.model_factory import ModeloDemanda

CRECIMIENTO_INTERVALO = 0.15


def factor_horizonte(h: int) -> float:
    return float(np.sqrt(1.0 + CRECIMIENTO_INTERVALO * (h - 1)))


class PredictorDemanda:
    def __init__(self, modelo: ModeloDemanda, preprocesador: PreprocesadorDemanda) -> None:
        self.modelo = modelo
        self.preprocesador = preprocesador

    def predecir(
        self, historial: pd.DataFrame, fecha_base: date, horizonte_dias: int
    ) -> list[PuntoPronostico]:
        """`historial`: ventas por día (`fecha`, `producto_id`, `ruta_id`, `cantidad`) hasta
        `fecha_base` inclusive; los días sin fila se asumen en 0."""
        base = pd.Timestamp(fecha_base)
        completo = completar_calendario(historial, hasta=base)
        series = self._series_con_historia(completo)

        claves = list(series)
        colas = np.stack([series[k][-HISTORIA_MINIMA_DIAS:] for k in claves])
        sal_pred = np.zeros((len(claves), horizonte_dias))
        for paso in range(horizonte_dias):
            fecha = base + pd.Timedelta(days=paso + 1)
            X = self._features_paso(claves, colas, fecha)
            pred = self.modelo.predecir(X)
            sal_pred[:, paso] = pred
            colas = np.concatenate([colas[:, 1:], pred[:, None]], axis=1)

        q_inf = min(self.preprocesador.residuo_q_inferior, 0.0)
        q_sup = max(self.preprocesador.residuo_q_superior, 0.0)
        puntos: list[PuntoPronostico] = []
        for i, (producto, ruta) in enumerate(claves):
            for paso in range(horizonte_dias):
                h = paso + 1
                y = float(sal_pred[i, paso])
                f = factor_horizonte(h)
                puntos.append(
                    PuntoPronostico(
                        producto_id=producto,
                        ruta_id=ruta,
                        fecha_objetivo=(base + pd.Timedelta(days=h)).date(),
                        horizonte_dias=h,
                        demanda=y,
                        inferior=max(0.0, y + q_inf * f),
                        superior=y + q_sup * f,
                    )
                )
        return puntos

    @staticmethod
    def _series_con_historia(completo: pd.DataFrame) -> dict[tuple[str, str], np.ndarray]:
        series: dict[tuple[str, str], np.ndarray] = {}
        insuficientes: list[str] = []
        for (producto, ruta), grupo in completo.groupby(COL_SERIE, sort=True):
            valores = grupo.sort_values("fecha")["cantidad"].to_numpy(dtype=float)
            if len(valores) < HISTORIA_MINIMA_DIAS:
                insuficientes.append(str(producto))
            else:
                series[(str(producto), str(ruta))] = valores
        if insuficientes or not series:
            raise HistorialInsuficiente(sorted(set(insuficientes)), HISTORIA_MINIMA_DIAS)
        return series

    def _features_paso(
        self, claves: list[tuple[str, str]], colas: np.ndarray, fecha: pd.Timestamp
    ) -> pd.DataFrame:
        """Características de `fecha` para cada serie; `colas[:, -1]` es `y_{t-1}`."""
        marco = pd.DataFrame(
            {
                "fecha": fecha,
                "producto_id": [k[0] for k in claves],
                "ruta_id": [k[1] for k in claves],
            }
        )
        for k in REZAGOS:
            marco[f"lag_{k}"] = colas[:, -k]
        for w in VENTANAS:
            marco[f"media_{w}"] = colas[:, -w:].mean(axis=1)
        return self.preprocesador.transformar(agregar_calendario(marco))
