"""Persistencia de `pronosticos_demanda`."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.models.ml import PronosticoDemanda

_UQ_PRONOSTICO = "uq_pronosticos_demanda_clave"


def upsert_pronosticos(db: Session, filas: Sequence[dict[str, Any]]) -> int:
    """Idempotente por `(modelo, producto, ruta, fecha_objetivo, horizonte)`: un nuevo cálculo
    reemplaza predicción e intervalo y conserva `demanda_real` ya registrada."""
    if not filas:
        return 0
    stmt = pg_insert(PronosticoDemanda).values(list(filas))
    stmt = stmt.on_conflict_do_update(
        constraint=_UQ_PRONOSTICO,
        set_={
            "demanda_predicha": stmt.excluded.demanda_predicha,
            "limite_inferior": stmt.excluded.limite_inferior,
            "limite_superior": stmt.excluded.limite_superior,
            "generado_en": stmt.excluded.generado_en,
        },
    )
    db.execute(stmt)
    return len(filas)
