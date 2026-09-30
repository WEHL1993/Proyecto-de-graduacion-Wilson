"""Contratos del módulo ML: tipos de intercambio, excepciones y fachada para `services/`.

`services/` invoca `ml/` **solo** desde aquí. Las funciones de fachada importan de forma
perezosa la implementación para evitar ciclos y mantener este módulo sin dependencias pesadas.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from sqlalchemy.orm import Session

from app.domain.enums import TipoEvaluacion
from app.ml.evaluation.metrics import MAPE_MAXIMO, Metricas
from app.ml.evaluation.metrics import calcular_metricas as _calcular_metricas

if TYPE_CHECKING:
    from app.domain.models.ml import ModeloML
    from app.ml.modeling.model_factory import ModeloDemanda


# ------------------------------------------------------------------ excepciones
class ErrorML(Exception):
    """Base de los errores del módulo ML."""


class DatosInsuficientes(ErrorML):
    """El histórico no alcanza para entrenar/evaluar."""


class HistorialInsuficiente(ErrorML):
    def __init__(self, productos: list[str], dias_minimos: int) -> None:
        self.productos = productos
        self.dias_minimos = dias_minimos
        super().__init__(f"Se requieren al menos {dias_minimos} días de historial por serie.")


class ArtefactoNoEncontrado(ErrorML):
    """Falta un archivo del modelo en `ml_artifacts`."""


class ArtefactoCorrupto(ErrorML):
    """El hash SHA-256 o el esquema del artefacto no coincide con lo registrado."""


# ------------------------------------------------------------------ tipos
@dataclass(frozen=True)
class PuntoPronostico:
    producto_id: str
    ruta_id: str
    fecha_objetivo: date
    horizonte_dias: int
    demanda: float
    inferior: float
    superior: float


@dataclass(frozen=True)
class MetricaCalculada:
    tipo_evaluacion: TipoEvaluacion
    producto_id: str | None
    metricas: Metricas
    periodo_desde: date
    periodo_hasta: date


@dataclass
class ResultadoEntrenamiento:
    modelo: "ModeloDemanda"
    preprocesador: Any
    hiperparametros: dict[str, Any]
    metricas: list[MetricaCalculada]
    ventana_desde: date
    ventana_hasta: date
    informe: dict[str, Any]


@dataclass(frozen=True)
class ArtefactoGuardado:
    ruta_relativa: str
    hash_modelo: str
    esquema_features: dict[str, Any]


class Predictor(Protocol):
    def predecir(
        self, historial: pd.DataFrame, fecha_base: date, horizonte_dias: int
    ) -> list[PuntoPronostico]: ...


# ------------------------------------------------------------------ fachada
def calcular_metricas(y_real: Any, y_pred: Any) -> Metricas:
    """MAE/RMSE/MAPE (definición única); el MAPE se satura a `MAPE_MAXIMO` (numeric(7,3))."""
    m = _calcular_metricas(y_real, y_pred)
    if m.mape is not None and m.mape > MAPE_MAXIMO:
        return Metricas(mae=m.mae, rmse=m.rmse, mape=MAPE_MAXIMO, n_muestras=m.n_muestras)
    return m


def entrenar_y_evaluar(
    ventas: pd.DataFrame, algoritmo: str, hiperparametros: dict[str, Any] | None = None
) -> ResultadoEntrenamiento:
    from app.ml.pipeline import entrenar_y_evaluar as _entrenar

    return _entrenar(ventas, algoritmo, hiperparametros)


def registrar_modelo(
    db: Session,
    *,
    nombre: str,
    algoritmo: str,
    resultado: ResultadoEntrenamiento,
    motivo: str,
    entrenado_por: uuid.UUID | None,
    raiz_artefactos: Path,
) -> "ModeloML":
    from app.ml.registry.model_registry import registrar_modelo as _registrar

    return _registrar(
        db,
        nombre=nombre,
        algoritmo=algoritmo,
        resultado=resultado,
        motivo=motivo,
        entrenado_por=entrenado_por,
        raiz_artefactos=raiz_artefactos,
    )


def promover_a_produccion(db: Session, modelo_id: uuid.UUID) -> "ModeloML":
    from app.ml.registry.model_registry import promover_a_produccion as _promover

    return _promover(db, modelo_id)


def cargar_predictor(
    *,
    modelo_id: uuid.UUID,
    raiz: Path,
    ruta_relativa: str,
    hash_artefacto: str,
    esquema_features: dict[str, Any],
) -> Predictor:
    """Predictor en caché; valida el SHA-256 al cargar desde disco."""
    from app.ml.inference.cache import obtener_predictor

    return obtener_predictor(
        modelo_id=modelo_id,
        raiz=raiz,
        ruta_relativa=ruta_relativa,
        hash_artefacto=hash_artefacto,
        esquema_features=esquema_features,
    )
