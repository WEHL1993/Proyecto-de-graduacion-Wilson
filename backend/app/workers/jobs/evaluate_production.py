"""Job `evaluate_production`: MAPE real vs. predicho del modelo productivo y detección de
degradación (TC-ML-01). Toda la lógica vive en `monitoring_service`."""

from datetime import date

from sqlalchemy.orm import Session

from app.services import job_service
from app.services.bitacora_service import auditar
from app.services.monitoring_service import ResultadoEvaluacion


@auditar
def ejecutar_en_cola(db: Session) -> None:
    """Atiende las evaluaciones encoladas por la API (p. ej. al cerrar una liquidación)."""
    while job_service.procesar_evaluacion_en_cola(db) is not None:
        pass


@auditar
def ejecutar(
    db: Session, *, desde: date | None = None, hasta: date | None = None
) -> ResultadoEvaluacion:
    """Evalúa los periodos pendientes (o `[desde, hasta]`); si el MAPE supera el umbral durante
    N periodos consecutivos crea la alerta `mape_umbral` y encola el reentrenamiento."""
    return job_service.ejecutar_evaluacion(db, desde=desde, hasta=hasta)
