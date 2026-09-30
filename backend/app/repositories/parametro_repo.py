"""Lectura de `parametros_sistema` (umbrales y tasas configurables)."""

from sqlalchemy.orm import Session

from app.domain.models.ml import ParametroSistema


def obtener_valor(db: Session, clave: str) -> object | None:
    parametro = db.get(ParametroSistema, clave)
    return None if parametro is None else parametro.valor
