"""Fixtures globales: la bitácora de auditoría (ADR-15) se apaga salvo en las pruebas que la
verifican (`@pytest.mark.bitacora`), para que no escriba en la BD real ni exija conexión."""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _bitacora_apagada(request, monkeypatch):
    activa = request.node.get_closest_marker("bitacora") is not None
    monkeypatch.setattr(get_settings(), "bitacora_habilitada", activa)


@pytest.fixture(autouse=True)
def _rbac_en_vivo_apagado(request, monkeypatch):
    """Las pruebas fabrican el JWT con sus permisos; `@pytest.mark.rbac_vivo` los lee de la BD."""
    activo = request.node.get_closest_marker("rbac_vivo") is not None
    monkeypatch.setattr(get_settings(), "rbac_permisos_en_vivo", activo)
