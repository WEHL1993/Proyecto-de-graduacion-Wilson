"""Particiones temporales Walk-Forward (ventana expansiva, sin fuga de datos).

Cada fold entrena con todas las fechas anteriores a `inicio_test - gap` y evalúa sobre los
`test_dias` siguientes. Ninguna fecha de prueba aparece antes de una de entrenamiento.
"""

from collections.abc import Iterator

import numpy as np
import pandas as pd


def walk_forward_splits(
    fechas: pd.Series,
    *,
    n_splits: int,
    test_dias: int,
    min_train_dias: int,
    gap_dias: int = 0,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Genera `(indices_train, indices_test)` posicionales sobre `fechas`.

    Los folds se alinean al final del rango: el último fold termina en la última fecha. Se
    generan menos de `n_splits` folds si el histórico no alcanza (nunca se acorta `min_train_dias`).
    """
    if n_splits < 1 or test_dias < 1 or min_train_dias < 1 or gap_dias < 0:
        raise ValueError("n_splits, test_dias y min_train_dias deben ser >= 1 y gap_dias >= 0.")
    valores = pd.to_datetime(fechas).reset_index(drop=True)
    primera, ultima = valores.min().normalize(), valores.max().normalize()
    un_dia = pd.Timedelta(days=1)

    for i in range(n_splits, 0, -1):
        fin_test = ultima - (i - 1) * test_dias * un_dia
        inicio_test = fin_test - (test_dias - 1) * un_dia
        fin_train = inicio_test - (gap_dias + 1) * un_dia
        if (fin_train - primera).days + 1 < min_train_dias:
            continue
        train = np.flatnonzero((valores <= fin_train).to_numpy())
        test = np.flatnonzero(((valores >= inicio_test) & (valores <= fin_test)).to_numpy())
        if train.size and test.size:
            yield train, test
