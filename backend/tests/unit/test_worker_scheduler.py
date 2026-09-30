"""Planificador del Worker sin base de datos: cadencia de la evaluación y tolerancia a fallos."""

from contextlib import contextmanager

import pytest

from app.workers import scheduler
from app.workers.scheduler import Planificador


class _Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


@contextmanager
def _sesion():
    yield object()


@pytest.fixture
def llamadas(monkeypatch):
    registro: list[str] = []
    monkeypatch.setattr(
        scheduler.evaluate_production, "ejecutar", lambda db: registro.append("evaluar")
    )
    monkeypatch.setattr(
        scheduler.retrain_model, "ejecutar_pendientes", lambda db: registro.append("reentrenar")
    )
    return registro


def test_evalua_en_el_primer_ciclo_y_luego_cada_intervalo(llamadas):
    reloj = _Reloj()
    plan = Planificador(fabrica_sesiones=_sesion, intervalo_evaluacion=100, reloj=reloj)

    plan.ciclo()
    assert llamadas == ["evaluar", "reentrenar"]

    reloj.ahora += 50  # aún no toca evaluar, pero sí vaciar la cola
    plan.ciclo()
    assert llamadas[2:] == ["reentrenar"]

    reloj.ahora += 50
    plan.ciclo()
    assert llamadas[3:] == ["evaluar", "reentrenar"]


def test_un_job_que_falla_no_detiene_al_worker(monkeypatch, llamadas):
    def _falla(db):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler.evaluate_production, "ejecutar", _falla)
    plan = Planificador(fabrica_sesiones=_sesion, intervalo_evaluacion=100, reloj=_Reloj())

    plan.ciclo()  # no propaga

    assert llamadas == ["reentrenar"]
