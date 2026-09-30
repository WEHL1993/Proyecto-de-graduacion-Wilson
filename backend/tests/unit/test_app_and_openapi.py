"""Pruebas sin base de datos: arranque de la app y sincronía del contrato OpenAPI exportado."""

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_exportado_esta_sincronizado():
    """Falla si se tocó un endpoint sin ejecutar `make openapi`."""
    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
