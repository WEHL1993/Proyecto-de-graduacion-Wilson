"""Ingeniería de características de la demanda diaria por serie (producto, ruta).

Todas las características de una fecha `t` usan solo información de fechas anteriores
(rezagos y medias móviles sobre `y_{t-1}` hacia atrás) o el calendario de `t`: no hay fuga.

Entrada esperada: DataFrame con columnas `fecha` (datetime64), `producto_id`, `ruta_id`
(ambas `str`) y `cantidad`, con **un registro por día calendario** dentro de cada serie.

Cobertura (ADR-14): con datos de Excel histórico y liquidaciones diarias separados por un hueco
sin información, solo se rellena con 0 dentro de los rangos cubiertos de cada ruta; los rezagos se
calculan por tramo contiguo (`segmento`) para no cruzar el hueco. Columna opcional `censurada`
(la demanda del día es un piso: se agotó el producto).
"""

from collections.abc import Mapping, Sequence
from datetime import date

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


# `ruta_id` (str) -> rangos de fechas (desde, hasta) con información para esa ruta.
Cobertura = Mapping[str, Sequence[tuple[date, date]]]


def _dias_cubiertos(
    rangos: Sequence[tuple[date, date]], desde: pd.Timestamp, hasta: pd.Timestamp
) -> pd.DatetimeIndex:
    """Unión ordenada de los días de `rangos` recortada a `[desde, hasta]`."""
    if not rangos:  # ruta sin cobertura declarada: tramo contiguo (comportamiento clásico)
        return pd.date_range(desde, hasta, freq="D")
    partes = []
    for ini, fin in rangos:
        a, b = max(pd.Timestamp(ini), desde), min(pd.Timestamp(fin), hasta)
        if a <= b:
            partes.append(pd.date_range(a, b, freq="D"))
    if not partes:
        return pd.DatetimeIndex([], dtype="datetime64[ns]")
    return partes[0].append(partes[1:]).unique().sort_values()


def _segmentos(indice: pd.DatetimeIndex) -> np.ndarray:
    """Identificador de tramo contiguo: aumenta cada vez que falta al menos un día."""
    if len(indice) == 0:
        return np.array([], dtype=int)
    saltos = np.diff(indice.values).astype("timedelta64[D]").astype(int) != 1
    return np.concatenate([[1], 1 + np.cumsum(saltos)])


def completar_calendario(
    df: pd.DataFrame, hasta: pd.Timestamp | None = None, cobertura: Cobertura | None = None
) -> pd.DataFrame:
    """Rellena con 0 los días sin venta de cada serie, desde su primera fecha hasta `hasta`
    (por defecto la última fecha del conjunto). Ausencia de fila en `ventas_historicas` = 0.

    Con `cobertura` el relleno se limita a los rangos cubiertos de cada ruta (los días sin
    información no son ceros) y se añade la columna `segmento`."""
    if df.empty:
        return df.copy()
    limite = hasta if hasta is not None else df["fecha"].max()
    con_censura = "censurada" in df.columns
    partes = []
    for (producto, ruta), grupo in df.groupby(COL_SERIE, sort=True):
        serie = grupo.groupby("fecha")["cantidad"].sum()
        if cobertura is None:
            indice = pd.date_range(serie.index.min(), limite, freq="D")
        else:
            cubiertos = _dias_cubiertos(cobertura.get(str(ruta), ()), serie.index.min(), limite)
            indice = cubiertos.union(serie.index[serie.index <= limite])
        columnas: dict[str, object] = {
            "fecha": indice,
            "producto_id": producto,
            "ruta_id": ruta,
            "cantidad": serie.reindex(indice, fill_value=0.0).to_numpy(dtype=float),
        }
        if cobertura is not None:
            columnas["segmento"] = _segmentos(indice)
        if con_censura:
            censura = grupo.groupby("fecha")["censurada"].max()
            columnas["censurada"] = censura.reindex(indice, fill_value=0.0).to_numpy(dtype=float)
        partes.append(pd.DataFrame(columnas))
    return pd.concat(partes, ignore_index=True)


def agregar_rezagos(df: pd.DataFrame) -> pd.DataFrame:
    """Lags `Y_{t-k}` y medias móviles de los `w` días previos a `t` (exclusivas de `t`)."""
    df = df.sort_values([*COL_SERIE, "fecha"]).reset_index(drop=True)
    # Con huecos de cobertura los rezagos se calculan dentro de cada tramo contiguo.
    claves = [*COL_SERIE, "segmento"] if "segmento" in df.columns else COL_SERIE
    por_serie = df.groupby(claves, sort=False)["cantidad"]
    for k in REZAGOS:
        df[f"lag_{k}"] = por_serie.shift(k)
    previo = por_serie.shift(1)
    llaves = [df[c] for c in claves]
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
