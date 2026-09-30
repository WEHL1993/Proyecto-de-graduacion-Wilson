"""Planificación del Worker: sondeo de la cola de reentrenamiento y evaluación periódica."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from app.workers.jobs import evaluate_production, retrain_model

logger = logging.getLogger(__name__)


@dataclass
class Planificador:
    """Un `ciclo()` atiende la cola de reentrenamientos y, si toca, evalúa producción."""

    fabrica_sesiones: sessionmaker[Session]
    intervalo_evaluacion: float
    reloj: Callable[[], float] = time.monotonic
    _proxima_evaluacion: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._proxima_evaluacion = self.reloj()  # evalúa en el primer ciclo

    def ciclo(self) -> None:
        if self.reloj() >= self._proxima_evaluacion:
            self._proxima_evaluacion = self.reloj() + self.intervalo_evaluacion
            self._proteger("evaluate_production", evaluate_production.ejecutar)
        self._proteger("retrain_model", retrain_model.ejecutar_pendientes)

    def _proteger(self, nombre: str, tarea: Callable[[Session], object]) -> None:
        """Un fallo en un job se registra y no detiene al Worker."""
        try:
            with self.fabrica_sesiones() as db:
                tarea(db)
        except Exception:
            logger.exception("Job %s falló", nombre)
