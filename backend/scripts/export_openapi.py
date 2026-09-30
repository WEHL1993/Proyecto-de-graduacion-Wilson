"""Vuelca el esquema OpenAPI de la app FastAPI en docs/architecture/openapi.yaml.

Uso (desde backend/):
    python scripts/export_openapi.py            # escribe el archivo
    python scripts/export_openapi.py --check    # falla (exit 1) si el archivo está desactualizado

Debe ejecutarse (`make openapi`) después de crear o modificar cualquier endpoint.
No requiere base de datos: el engine de SQLAlchemy se crea de forma perezosa.
"""

import argparse
import sys
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

DEFAULT_OUTPUT = BACKEND_DIR.parent / "docs" / "architecture" / "openapi.yaml"
HEADER = (
    "# ARCHIVO GENERADO por backend/scripts/export_openapi.py — no editar a mano.\n"
    "# Regenerar con `make openapi`. Diseño de referencia: openapi.contract.yaml\n"
)


def render() -> str:
    body = yaml.safe_dump(app.openapi(), sort_keys=False, allow_unicode=True, width=100)
    return HEADER + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="solo verificar, no escribir")
    args = parser.parse_args()

    content = render()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != content:
            print(
                f"[ERROR] {args.output} está desactualizado. Ejecuta `make openapi`.",
                file=sys.stderr,
            )
            return 1
        print(f"[OK] {args.output} está sincronizado.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    print(f"[OK] Contrato OpenAPI exportado en {args.output} ({len(app.openapi()['paths'])} rutas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
