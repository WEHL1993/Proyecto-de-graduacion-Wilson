"""Lectura de `parametros_sistema` (umbrales y tasas configurables)."""

import uuid

from sqlalchemy.orm import Session

from app.domain.models.ml import ParametroSistema


def obtener_valor(db: Session, clave: str) -> object | None:
    parametro = db.get(ParametroSistema, clave)
    return None if parametro is None else parametro.valor


def guardar_valor(
    db: Session, clave: str, valor: object, *, actualizado_por: uuid.UUID | None = None
) -> None:
    parametro = db.get(ParametroSistema, clave)
    if parametro is None:
        db.add(ParametroSistema(clave=clave, valor=valor, actualizado_por=actualizado_por))
    else:
        parametro.valor = valor
        parametro.actualizado_por = actualizado_por
    db.flush()
