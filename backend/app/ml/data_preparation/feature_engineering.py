"""Ingeniería de características de la demanda diaria por serie (producto, ruta).

Todas las características de una fecha `t` usan solo información de fechas anteriores
(rezagos y medias móviles sobre `y_{t-1}` hacia atrás) o el calendario de `t`: no hay fuga.

Entrada esperada: DataFrame con columnas `fecha` (datetime64), `producto_id`, `ruta_id`
(ambas `str`) y `cantidad`, con **un registro por día calendario** dentro de cada serie.
"""

import numpy as np
import pandas as pd

COL_SERIE = ["producto_id", "ruta_id"]
REZAGOS = (1, 7, 14)
VENTANAS = (7, 14, 28)
# Historia mínima por serie para que todas las características del primer día a predecir existan.
HISTORIA_MINIMA_DIAS = max(max(REZAGOS), max(VENTANAS))

FEATURES_REZAGO = [f"lag_{k}" for k in REZAGOS] + [f"media_{w}" for w in VENTANAS]
FEATURES_CALENDARIO = [
    "dia_semana",
    "dia_mes",
    "quincena",
    "es_fin_quincena",
    "mes",
    "dia_semana_sin",
    "dia_semana_cos",
    "dia_anio_sin",
    "dia_anio_cos",
]


def completar_calendario(df: pd.DataFrame, hasta: pd.Timestamp | None = None) -> pd.DataFrame:
    """Rellena con 0 los días sin venta de cada serie, desde su primera fecha hasta `hasta`
    (por defecto la última fecha del conjunto). Ausencia de fila en `ventas_historicas` = 0."""
    if df.empty:
        return df.copy()
    limite = hasta if hasta is not None else df["fecha"].max()
    partes = []
    for (producto, ruta), grupo in df.groupby(COL_SERIE, sort=True):
        serie = grupo.groupby("fecha")["cantidad"].sum()
        indice = pd.date_range(serie.index.min(), limite, freq="D")
        serie = serie.reindex(indice, fill_value=0.0)
        partes.append(
            pd.DataFrame(
                {
                    "fecha": indice,
                    "producto_id": producto,
                    "ruta_id": ruta,
                    "cantidad": serie.to_numpy(dtype=float),
                }
            )
        )
    return pd.concat(partes, ignore_index=True)


def agregar_rezagos(df: pd.DataFrame) -> pd.DataFrame:
    """Lags `Y_{t-k}` y medias móviles de los `w` días previos a `t` (exclusivas de `t`)."""
    df = df.sort_values([*COL_SERIE, "fecha"]).reset_index(drop=True)
    por_serie = df.groupby(COL_SERIE, sort=False)["cantidad"]
    for k in REZAGOS:
        df[f"lag_{k}"] = por_serie.shift(k)
    previo = por_serie.shift(1)
    llaves = [df[c] for c in COL_SERIE]
    for w in VENTANAS:
        df[f"media_{w}"] = previo.groupby(llaves, sort=False).transform(
            lambda s, w=w: s.rolling(w, min_periods=w).mean()
        )
    return df


def agregar_calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Día de semana, quincena, mes y estacionalidad cíclica (semanal y anual)."""
    df = df.copy()
    fecha = df["fecha"]
    df["dia_semana"] = fecha.dt.dayofweek
    df["dia_mes"] = fecha.dt.day
    df["quincena"] = np.where(fecha.dt.day <= 15, 1, 2)
    # Días de pago típicos: el 15 y el último día del mes.
    df["es_fin_quincena"] = ((fecha.dt.day == 15) | fecha.dt.is_month_end).astype(int)
    df["mes"] = fecha.dt.month
    df["dia_semana_sin"] = np.sin(2 * np.pi * df["dia_semana"] / 7)
    df["dia_semana_cos"] = np.cos(2 * np.pi * df["dia_semana"] / 7)
    anio = fecha.dt.dayofyear / np.where(fecha.dt.is_leap_year, 366, 365)
    df["dia_anio_sin"] = np.sin(2 * np.pi * anio)
    df["dia_anio_cos"] = np.cos(2 * np.pi * anio)
    return df


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calendario + rezagos. Las filas sin historia suficiente conservan NaN en los rezagos."""
    return agregar_calendario(agregar_rezagos(df))
