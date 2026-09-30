"""Lectura/escritura de artefactos en `ml_artifacts/models/<algoritmo>/<version>/`.

Archivos: `model.bin`, `preprocessor.bin`, `feature_schema.json`, `training_report.json`.
Una versión es inmutable (no se sobrescribe). La integridad se verifica con SHA-256:
`hash_artefacto` (BD) = hash de `model.bin`; el hash de `preprocessor.bin` viaja en
`esquema_features["preprocessor_sha256"]` (también en BD).
"""

import hashlib
import json
from pathlib import Path

import joblib

from app.ml.contracts import ArtefactoCorrupto, ArtefactoGuardado, ArtefactoNoEncontrado
from app.ml.data_preparation.preprocessor import PreprocesadorDemanda
from app.ml.modeling.model_factory import ModeloDemanda

MODELO = "model.bin"
PREPROCESADOR = "preprocessor.bin"
ESQUEMA = "feature_schema.json"
REPORTE = "training_report.json"


def calcular_sha256(ruta: Path) -> str:
    resumen = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def _directorio(raiz: Path, ruta_relativa: str) -> Path:
    destino = (raiz / ruta_relativa).resolve()
    if not destino.is_relative_to(raiz.resolve()):
        raise ArtefactoCorrupto(f"Ruta de artefacto fuera de ml_artifacts: {ruta_relativa!r}")
    return destino


def guardar_artefactos(
    raiz: Path,
    *,
    algoritmo: str,
    version: str,
    modelo: ModeloDemanda,
    preprocesador: PreprocesadorDemanda,
    informe: dict,
) -> ArtefactoGuardado:
    ruta_relativa = f"models/{algoritmo}/{version}"
    directorio = _directorio(raiz, ruta_relativa)
    directorio.mkdir(parents=True, exist_ok=False)  # FileExistsError: versión ya publicada

    joblib.dump(modelo, directorio / MODELO)
    joblib.dump(preprocesador, directorio / PREPROCESADOR)
    esquema = {
        "features": list(preprocesador.features),
        "preprocessor_sha256": calcular_sha256(directorio / PREPROCESADOR),
    }
    (directorio / ESQUEMA).write_text(json.dumps(esquema, indent=2), encoding="utf-8")
    (directorio / REPORTE).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return ArtefactoGuardado(
        ruta_relativa=ruta_relativa,
        hash_modelo=calcular_sha256(directorio / MODELO),
        esquema_features=esquema,
    )


def cargar_artefactos(
    raiz: Path, ruta_relativa: str, hash_modelo: str, esquema_features: dict
) -> tuple[ModeloDemanda, PreprocesadorDemanda]:
    """Verifica los SHA-256 **antes** de deserializar (joblib/pickle ejecuta código al cargar)."""
    directorio = _directorio(raiz, ruta_relativa)
    archivo_modelo, archivo_prep = directorio / MODELO, directorio / PREPROCESADOR
    for archivo in (archivo_modelo, archivo_prep):
        if not archivo.is_file():
            raise ArtefactoNoEncontrado(f"Falta el artefacto {archivo.name} en {ruta_relativa}")

    if calcular_sha256(archivo_modelo) != hash_modelo:
        raise ArtefactoCorrupto(f"El hash SHA-256 de {MODELO} no coincide con el registrado")
    if calcular_sha256(archivo_prep) != esquema_features.get("preprocessor_sha256"):
        raise ArtefactoCorrupto(f"El hash SHA-256 de {PREPROCESADOR} no coincide con el registrado")

    modelo = joblib.load(archivo_modelo)
    preprocesador = joblib.load(archivo_prep)
    if list(preprocesador.features) != list(esquema_features.get("features", [])):
        raise ArtefactoCorrupto("El esquema de features del preprocesador no coincide con la BD")
    return modelo, preprocesador
