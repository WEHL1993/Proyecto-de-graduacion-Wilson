"""Caso de uso: entrenar, evaluar y registrar un modelo de demanda (motivo `manual`/`programado`).

El modelo queda como `candidato`; solo pasa a `produccion` con `promover=True` (ADR-03).
"""

import uuid

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import MotivoEntrenamiento
from app.domain.models.ml import ModeloML
from app.ml import contracts
from app.repositories import sales_repo


def entrenar_modelo(
    db: Session,
    *,
    algoritmo: str,
    hiperparametros: dict | None = None,
    motivo: MotivoEntrenamiento = MotivoEntrenamiento.MANUAL,
    entrenado_por: uuid.UUID | None = None,
    promover: bool = False,
) -> ModeloML:
    settings = get_settings()
    filas = sales_repo.ventas_diarias(db)
    ventas = pd.DataFrame(
        {
            "fecha": pd.to_datetime([f[0] for f in filas]),
            "producto_id": [str(f[1]) for f in filas],
            "ruta_id": [str(f[2]) for f in filas],
            "cantidad": [float(f[3]) for f in filas],
        }
    )
    try:
        resultado = contracts.entrenar_y_evaluar(ventas, algoritmo, hiperparametros)
    except contracts.DatosInsuficientes as exc:
        raise AppError("DATOS_INSUFICIENTES", str(exc)) from exc
    except ValueError as exc:  # algoritmo no soportado
        raise AppError("ALGORITMO_NO_SOPORTADO", str(exc)) from exc

    modelo = contracts.registrar_modelo(
        db,
        nombre=settings.ml_modelo_nombre,
        algoritmo=algoritmo,
        resultado=resultado,
        motivo=motivo.value,
        entrenado_por=entrenado_por,
        raiz_artefactos=settings.ml_artifacts_dir,
    )
    if promover:
        contracts.promover_a_produccion(db, modelo.id)
    db.commit()
    return modelo
