"""Pipeline de entrenamiento y evaluación (CRISP-DM: preparación → modelado → evaluación).

1. Preparación: calendario completo por serie, rezagos, medias móviles y calendario.
2. Backtest Walk-Forward (1 paso, ventana expansiva): métricas `backtest` y residuos que
   calibran el intervalo al 95 %.
3. Holdout recursivo: se reserva el último tramo (`horizonte_holdout` días), se entrena con
   lo anterior y se pronostica con el mismo `PredictorDemanda` de producción: métricas
   `holdout` globales y por producto, y cobertura empírica del intervalo.
4. Modelo final: se reentrena con todo el histórico.

ADR-14: con `cobertura` (Excel histórico + liquidaciones separados por un hueco) el calendario
solo se completa dentro de los rangos cubiertos y los rezagos no cruzan el hueco. Las
observaciones `censurada` (producto agotado: la venta es un piso de la demanda) pesan
`PESO_OBSERVACION_CENSURADA` en el entrenamiento.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from app.domain.enums import TipoEvaluacion
from app.ml.contracts import (
    DatosInsuficientes,
    MetricaCalculada,
    ResultadoEntrenamiento,
)
from app.ml.data_preparation.feature_engineering import (
    COL_SERIE,
    FEATURES_REZAGO,
    HISTORIA_MINIMA_DIAS,
    Cobertura,
    completar_calendario,
    construir_features,
)
from app.ml.data_preparation.preprocessor import PreprocesadorDemanda
from app.ml.data_preparation.splitters import walk_forward_splits
from app.ml.evaluation.metrics import MAPE_MAXIMO, calcular_metricas
from app.ml.inference.predictor import PredictorDemanda
from app.ml.modeling.model_factory import ModeloDemanda, crear_modelo

NIVEL_INTERVALO = 0.95
PESO_OBSERVACION_CENSURADA = 0.5


@dataclass(frozen=True)
class ConfigEntrenamiento:
    n_splits: int = 3
    test_dias: int = 14
    min_train_dias: int = 60
    horizonte_holdout: int = 14


def _ajustar(
    algoritmo: str, hiperparametros: dict, dataset: pd.DataFrame
) -> tuple[ModeloDemanda, PreprocesadorDemanda]:
    prep = PreprocesadorDemanda().ajustar(dataset)
    modelo = crear_modelo(algoritmo, **hiperparametros)
    pesos = dataset["peso"].to_numpy(dtype=float) if "peso" in dataset.columns else None
    modelo.entrenar(prep.transformar(dataset), dataset["cantidad"].to_numpy(dtype=float), pesos)
    return modelo, prep


def _metrica(tipo: TipoEvaluacion, y, pred, desde, hasta, producto_id=None) -> MetricaCalculada:
    m = calcular_metricas(y, pred)
    if m.mape is not None:
        m = replace(m, mape=min(m.mape, MAPE_MAXIMO))
    return MetricaCalculada(tipo, producto_id, m, desde, hasta)


def entrenar_y_evaluar(
    ventas: pd.DataFrame,
    algoritmo: str,
    hiperparametros: dict | None = None,
    config: ConfigEntrenamiento | None = None,
    cobertura: Cobertura | None = None,
) -> ResultadoEntrenamiento:
    """`ventas`: `fecha`, `producto_id`, `ruta_id`, `cantidad` (una fila por día con venta) y,
    opcional, `censurada` (0/1)."""
    cfg = config or ConfigEntrenamiento()
    hp = dict(hiperparametros or {})
    if ventas.empty:
        raise DatosInsuficientes("No hay ventas históricas para entrenar.")

    ventas = ventas.assign(
        fecha=pd.to_datetime(ventas["fecha"]),
        producto_id=ventas["producto_id"].astype(str),
        ruta_id=ventas["ruta_id"].astype(str),
        cantidad=ventas["cantidad"].astype(float),
    )
    completo = completar_calendario(ventas, cobertura=cobertura)
    dataset = construir_features(completo).dropna(subset=FEATURES_REZAGO).reset_index(drop=True)
    n_censuradas = 0
    if "censurada" in dataset.columns:
        n_censuradas = int((dataset["censurada"] > 0).sum())
        dataset["peso"] = 1.0 - (1.0 - PESO_OBSERVACION_CENSURADA) * (dataset["censurada"] > 0)
    desde, hasta = completo["fecha"].min().date(), completo["fecha"].max().date()

    # ---- backtest Walk-Forward (1 paso)
    reales, predichos, residuos = [], [], []
    inicio_bt, fin_bt = None, None
    for idx_train, idx_test in walk_forward_splits(
        dataset["fecha"],
        n_splits=cfg.n_splits,
        test_dias=cfg.test_dias,
        min_train_dias=cfg.min_train_dias,
    ):
        train, test = dataset.iloc[idx_train], dataset.iloc[idx_test]
        modelo, prep = _ajustar(algoritmo, hp, train)
        pred = modelo.predecir(prep.transformar(test))
        y = test["cantidad"].to_numpy(dtype=float)
        reales.append(y)
        predichos.append(pred)
        residuos.append(y - pred)
        inicio_bt = inicio_bt or test["fecha"].min().date()
        fin_bt = test["fecha"].max().date()
    if not reales:
        raise DatosInsuficientes(
            f"Histórico insuficiente: se requieren al menos "
            f"{HISTORIA_MINIMA_DIAS + cfg.min_train_dias + cfg.test_dias} días por serie "
            f"(hay {(hasta - desde).days + 1})."
        )
    y_bt, p_bt, r_bt = map(np.concatenate, (reales, predichos, residuos))
    metricas = [_metrica(TipoEvaluacion.BACKTEST, y_bt, p_bt, inicio_bt, fin_bt)]
    q_inf, q_sup = np.quantile(r_bt, [(1 - NIVEL_INTERVALO) / 2, (1 + NIVEL_INTERVALO) / 2])

    # ---- holdout recursivo con el predictor de producción
    corte = pd.Timestamp(hasta) - pd.Timedelta(days=cfg.horizonte_holdout)
    entrenamiento = dataset[dataset["fecha"] <= corte]
    if entrenamiento.empty:
        raise DatosInsuficientes("El histórico no alcanza para reservar el holdout.")
    modelo_h, prep_h = _ajustar(algoritmo, hp, entrenamiento)
    prep_h.residuo_q_inferior, prep_h.residuo_q_superior = float(q_inf), float(q_sup)
    historial = ventas[ventas["fecha"] <= corte]
    puntos = PredictorDemanda(modelo_h, prep_h).predecir(
        historial, corte.date(), cfg.horizonte_holdout, cobertura=cobertura
    )
    cobertura_intervalo = _metricas_holdout(completo, puntos, metricas)

    # ---- modelo final con todo el histórico
    modelo, prep = _ajustar(algoritmo, hp, dataset)
    prep.residuo_q_inferior, prep.residuo_q_superior = float(q_inf), float(q_sup)
    informe = {
        "algoritmo": algoritmo,
        "hiperparametros": modelo.hiperparametros,
        "ventana": {"desde": desde, "hasta": hasta},
        "n_filas_entrenamiento": len(dataset),
        "n_series": len(prep.codigos_serie),
        "con_cobertura": cobertura is not None,
        "n_observaciones_censuradas": n_censuradas,
        "peso_observacion_censurada": PESO_OBSERVACION_CENSURADA,
        "configuracion": cfg.__dict__,
        "cobertura_intervalo_holdout": cobertura_intervalo,
        "nivel_intervalo": NIVEL_INTERVALO,
        "metricas": [
            {
                "tipo": m.tipo_evaluacion.value,
                "producto_id": m.producto_id,
                "mae": m.metricas.mae,
                "rmse": m.metricas.rmse,
                "mape": m.metricas.mape,
                "n_muestras": m.metricas.n_muestras,
            }
            for m in metricas
        ],
    }
    return ResultadoEntrenamiento(
        modelo=modelo,
        preprocesador=prep,
        hiperparametros=modelo.hiperparametros,
        metricas=metricas,
        ventana_desde=desde,
        ventana_hasta=hasta,
        informe=informe,
    )


def _metricas_holdout(
    completo: pd.DataFrame, puntos: list, metricas: list[MetricaCalculada]
) -> float:
    """Agrega métricas `holdout` (global y por producto) y devuelve la cobertura del intervalo."""
    pron = pd.DataFrame([p.__dict__ for p in puntos]).rename(columns={"fecha_objetivo": "fecha"})
    pron["fecha"] = pd.to_datetime(pron["fecha"])
    real = completo.merge(pron, on=[*COL_SERIE, "fecha"], how="inner")
    if real.empty:
        return float("nan")
    desde, hasta = real["fecha"].min().date(), real["fecha"].max().date()
    y, pred = real["cantidad"].to_numpy(), real["demanda"].to_numpy()
    metricas.append(_metrica(TipoEvaluacion.HOLDOUT, y, pred, desde, hasta))
    for producto, grupo in real.groupby("producto_id"):
        metricas.append(
            _metrica(
                TipoEvaluacion.HOLDOUT,
                grupo["cantidad"],
                grupo["demanda"],
                desde,
                hasta,
                producto_id=producto,
            )
        )
    dentro = (real["cantidad"] >= real["inferior"]) & (real["cantidad"] <= real["superior"])
    return float(dentro.mean())
