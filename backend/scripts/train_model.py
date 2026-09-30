"""Entrena y registra un modelo de demanda con el histórico de `ventas_historicas`.

Uso (desde backend/):
    python scripts/train_model.py --algoritmo xgboost [--promover]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_sessionmaker  # noqa: E402
from app.services import training_service  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algoritmo", choices=["sklearn", "xgboost"], default="xgboost")
    parser.add_argument("--promover", action="store_true", help="Promueve el modelo a producción")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        modelo = training_service.entrenar_modelo(
            db, algoritmo=args.algoritmo, promover=args.promover
        )
        print(f"Modelo {modelo.nombre} {modelo.version} ({modelo.algoritmo}) -> {modelo.estado}")
        print(f"Artefactos: ml_artifacts/{modelo.ruta_artefacto}  sha256={modelo.hash_artefacto}")


if __name__ == "__main__":
    main()
