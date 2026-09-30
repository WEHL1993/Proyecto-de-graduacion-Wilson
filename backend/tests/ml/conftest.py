"""Datos sintéticos deterministas para las pruebas del pipeline ML."""

import uuid

import numpy as np
import pandas as pd
import pytest

PRODUCTO_A = str(uuid.UUID(int=1))
PRODUCTO_B = str(uuid.UUID(int=2))
RUTA_1 = str(uuid.UUID(int=101))
RUTA_2 = str(uuid.UUID(int=102))
FECHA_FIN = pd.Timestamp("2025-12-31")
DIAS = 240


def generar_ventas(dias: int = DIAS, semilla: int = 7) -> pd.DataFrame:
    """2 productos × 2 rutas, con patrón semanal y de quincena más ruido; sin domingos."""
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range(end=FECHA_FIN, periods=dias, freq="D")
    filas = []
    for producto, base in ((PRODUCTO_A, 40.0), (PRODUCTO_B, 15.0)):
        for ruta, escala in ((RUTA_1, 1.0), (RUTA_2, 0.6)):
            for fecha in fechas:
                if fecha.dayofweek == 6:
                    continue
                patron = 1.0 + 0.4 * (fecha.dayofweek in (4, 5)) + 0.2 * (fecha.day in (15, 30))
                cantidad = max(0.0, base * escala * patron + rng.normal(0, base * 0.05))
                filas.append((fecha, producto, ruta, round(cantidad, 2)))
    return pd.DataFrame(filas, columns=["fecha", "producto_id", "ruta_id", "cantidad"])


@pytest.fixture(scope="session")
def ventas() -> pd.DataFrame:
    return generar_ventas()
