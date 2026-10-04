"""Job `retrain_model`: consume la cola `jobs_ml` de reentrenamientos.

Entrena el candidato en segundo plano y solo lo promueve si supera al modelo productivo
(`retraining_service`)."""

import uuid

from sqlalchemy.orm import Session

from app.services import job_service
from app.services.bitacora_service import auditar


@auditar
def ejecutar(db: Session) -> uuid.UUID | None:
    """Procesa el reentrenamiento más antiguo en cola; `None` si la cola está vacía."""
    return job_service.procesar_siguiente_reentrenamiento(db)


@auditar
def ejecutar_pendientes(db: Session) -> list[uuid.UUID]:
    """Vacía la cola de reentrenamientos y devuelve los ids procesados."""
    procesados: list[uuid.UUID] = []
    while (job_id := ejecutar(db)) is not None:
        procesados.append(job_id)
    return procesados
