"""DTOs de gobernanza ML (`/ml/*`, sección 4 de `openapi.contract.yaml` + ADR-12)."""

from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    Algoritmo,
    EstadoJob,
    EstadoModelo,
    MotivoEntrenamiento,
    TipoJob,
)


# ------------------------------------------------------------------ GET /ml/metrics
class MetricPoint(BaseModel):
    periodo_desde: date
    periodo_hasta: date
    mae: float
    rmse: float
    mape: float | None = None
    n_muestras: int
    supera_umbral: bool = False


class ResumenMetricas(BaseModel):
    """Valores del periodo más reciente de la serie (KPI del panel)."""

    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None


class PeorProducto(BaseModel):
    producto_id: UUID
    sku: str | None = None
    nombre: str | None = None
    mae: float
    rmse: float
    mape: float | None = None
    tendencia: Literal["sube", "baja", "estable"] | None = Field(
        default=None, description="MAPE del último periodo frente al anterior"
    )


class Degradacion(BaseModel):
    umbral_mape: float
    periodos_consecutivos_requeridos: int
    periodos_consecutivos_actuales: int
    requiere_reentrenamiento: bool
    ultimo_reentrenamiento: datetime | None = None
    ultimo_reentrenamiento_resultado: EstadoModelo | None = Field(
        default=None, description="Estado final del candidato del último reentrenamiento"
    )


class ModeloInfo(BaseModel):
    id: UUID
    nombre: str
    algoritmo: Algoritmo
    version: str
    estado: EstadoModelo


class MetricsResponse(BaseModel):
    modelo_id: UUID
    modelo: ModeloInfo
    resumen: ResumenMetricas
    serie: list[MetricPoint]
    peores_productos: list[PeorProducto] = Field(default_factory=list)
    degradacion: Degradacion


# ------------------------------------------------------------------ POST /ml/models/retrain
class RetrainRequest(BaseModel):
    algoritmos: list[Algoritmo] = Field(min_length=1)
    motivo: MotivoEntrenamiento
    ventana_desde: date | None = None
    ventana_hasta: date | None = None
    promover_automaticamente: bool = Field(
        default=True, description="Promueve si el candidato mejora el MAPE del modelo en producción"
    )

    @model_validator(mode="after")
    def _ventana_coherente(self) -> Self:
        if self.ventana_desde and self.ventana_hasta and self.ventana_desde >= self.ventana_hasta:
            raise ValueError("`ventana_desde` debe ser anterior a `ventana_hasta`.")
        if len(set(self.algoritmos)) != len(self.algoritmos):
            raise ValueError("`algoritmos` no puede repetir valores.")
        return self


class RetrainResponse(BaseModel):
    job_id: UUID
    estado: Literal["en_cola", "en_ejecucion"]
    solicitado_en: datetime


# ------------------------------------------------------------------ extensiones (ADR-12)
class JobStatus(BaseModel):
    job_id: UUID
    tipo: TipoJob
    estado: EstadoJob
    parametros: dict
    resultado_modelo_id: UUID | None = None
    solicitado_en: datetime
    iniciado_en: datetime | None = None
    finalizado_en: datetime | None = None
    error: str | None = None


class ModeloResumen(BaseModel):
    id: UUID
    version: str
    algoritmo: Algoritmo
    estado: EstadoModelo
    motivo_entrenamiento: MotivoEntrenamiento
    entrenado_en: datetime
    promovido_en: datetime | None = None
    mape_holdout: float | None = None


class ModelList(BaseModel):
    modelos: list[ModeloResumen]


class MlConfig(BaseModel):
    umbral_mape: float = Field(gt=0, le=1000)
    periodos_consecutivos: int = Field(ge=1, le=52)
