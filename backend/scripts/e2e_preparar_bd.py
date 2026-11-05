"""Prepara una BD **aislada y desechable** para las pruebas E2E de Playwright.

Uso (desde backend/; lo invoca `frontend/playwright.config.ts` antes de levantar la API):

    python scripts/e2e_preparar_bd.py

1. Borra y recrea la base indicada por `DATABASE_URL` (debe llamarse *_e2e, por seguridad) y
   vacía `ML_ARTIFACTS_DIR` si está dentro de `frontend/e2e/.tmp`.
2. Aplica las migraciones Alembic y el seed de RBAC (admin, roles, pantallas, parámetros).
3. Importa los catálogos reales desde `data/raw` (productos, rutas, alias de Excel).
4. Genera `frontend/e2e/.tmp/historico_sintetico.xlsx`: 90 días (dic-2024 a feb-2025) en formato
   **tabular** para las series con ventas en el Excel de marzo 2025. El Excel real solo trae 31
   días y el pipeline exige ≥ 49 por serie, así que sin este archivo no se puede entrenar.
"""

import math
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
SALIDA = BACKEND_DIR.parent / "frontend" / "e2e" / ".tmp"

# (ruta, sku, demanda media diaria, precio). Son series con ventas reales en marzo 2025.
SERIES = [
    ("ANTONIO", "599033", 27, 50.0),
    ("ANTONIO", "521733", 17, 40.0),
    ("ANTONIO", "500179", 28, 61.0),
    ("CESAR", "500179", 30, 61.0),
    ("CESAR", "500390", 21, 41.0),
    ("CESAR", "599032", 17, 50.0),
    ("CORNELIO", "599033", 17, 50.0),
    ("CORNELIO", "500179", 17, 61.0),
]
INICIO, DIAS = date(2024, 12, 1), 90


def _recrear_bd(url: str) -> None:
    destino = make_url(url)
    if not (destino.database or "").endswith("_e2e"):
        sys.exit(f"Por seguridad la BD de E2E debe terminar en _e2e (recibido: {destino.database})")
    admin = create_engine(destino.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{destino.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{destino.database}"'))
    admin.dispose()


def _limpiar_artefactos() -> None:
    """Vacía los artefactos ML junto con la BD: el registro numera las versiones desde la BD."""
    destino = Path(os.environ.get("ML_ARTIFACTS_DIR", "")).resolve()
    if SALIDA.resolve() in destino.parents:  # solo dentro de frontend/e2e/.tmp
        shutil.rmtree(destino, ignore_errors=True)


def _ejecutar(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=BACKEND_DIR, check=True)


def _historico_sintetico() -> Path:
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "ventas"
    hoja.append(["fecha", "ruta", "sku", "cantidad", "precio_unitario"])
    for i in range(DIAS):
        dia = INICIO + timedelta(days=i)
        semanal = 1 + 0.25 * math.sin(2 * math.pi * dia.weekday() / 7)
        for k, (ruta, sku, media, precio) in enumerate(SERIES):
            ruido = 1 + 0.1 * math.sin(i * 1.7 + k)  # determinista: misma data en cada corrida
            hoja.append([dia, ruta, sku, max(1, round(media * semanal * ruido)), precio])
    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / "historico_sintetico.xlsx"
    libro.save(destino)
    return destino


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Defina DATABASE_URL apuntando a la BD de E2E (…/ds_e2e)")
    _recrear_bd(url)
    _limpiar_artefactos()
    _ejecutar("-m", "alembic", "upgrade", "head")
    _ejecutar("-m", "app.db.seeds.seed_rbac")
    _ejecutar("-m", "app.db.seeds.importar_catalogos", "--aplicar", "--auto-alias")
    print(f"[OK] BD E2E lista; histórico sintético en {_historico_sintetico()}")


if __name__ == "__main__":
    main()
