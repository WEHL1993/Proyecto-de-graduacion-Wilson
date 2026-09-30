"""Caché en memoria del predictor del modelo productivo.

La clave incluye el hash registrado en `modelos_ml`: si se promueve otra versión o cambia el
hash en BD, la entrada anterior deja de usarse y se recarga (validando SHA-256 del disco).
"""

import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from app.ml.inference.predictor import PredictorDemanda
from app.ml.registry.artifact_store import cargar_artefactos

_MAX_ENTRADAS = 4
_cache: OrderedDict[tuple[uuid.UUID, str], PredictorDemanda] = OrderedDict()
_lock = threading.Lock()


def obtener_predictor(
    *,
    modelo_id: uuid.UUID,
    raiz: Path,
    ruta_relativa: str,
    hash_artefacto: str,
    esquema_features: dict,
) -> PredictorDemanda:
    clave = (modelo_id, hash_artefacto)
    with _lock:
        if clave in _cache:
            _cache.move_to_end(clave)
            return _cache[clave]
        modelo, preprocesador = cargar_artefactos(
            raiz, ruta_relativa, hash_artefacto, esquema_features
        )
        predictor = PredictorDemanda(modelo, preprocesador)
        # Solo una versión por modelo: descarta entradas obsoletas del mismo id.
        for otra in [k for k in _cache if k[0] == modelo_id]:
            del _cache[otra]
        _cache[clave] = predictor
        while len(_cache) > _MAX_ENTRADAS:
            _cache.popitem(last=False)
        return predictor


def limpiar_cache() -> None:
    with _lock:
        _cache.clear()
