"""Punto de entrada del Worker Predictivo (proceso separado del API).

python -m app.workers.main
"""

import logging
import signal
import threading

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.workers.scheduler import Planificador

logger = logging.getLogger("app.workers")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    detener = threading.Event()
    for senal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(senal, lambda *_: detener.set())

    planificador = Planificador(
        fabrica_sesiones=get_sessionmaker(),
        intervalo_evaluacion=settings.worker_evaluacion_intervalo_segundos,
    )
    logger.info(
        "Worker iniciado (sondeo %ss, evaluación cada %ss)",
        settings.worker_poll_segundos,
        settings.worker_evaluacion_intervalo_segundos,
    )
    while not detener.is_set():
        planificador.ciclo()
        detener.wait(settings.worker_poll_segundos)
    logger.info("Worker detenido")


if __name__ == "__main__":
    main()
