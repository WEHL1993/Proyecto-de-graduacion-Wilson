"""Fixtures globales: la bitácora de auditoría (ADR-15) se apaga salvo en las pruebas que la
verifican (`@pytest.mark.bitacora`), para que no escriba en la BD real ni exija conexión."""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _bitacora_apagada(request, monkeypatch):
    activa = request.node.get_closest_marker("bitacora") is not None
    monkeypatch.setattr(get_settings(), "bitacora_habilitada", activa)
