"""Persistencia de alertas del sistema."""

from sqlalchemy.orm import Session

from app.domain.enums import Severidad, TipoAlerta
from app.domain.models.ml import Alerta


def crear(db: Session, *, tipo: TipoAlerta, severidad: Severidad, mensaje: str) -> Alerta:
    alerta = Alerta(tipo=tipo, severidad=severidad, mensaje=mensaje)
    db.add(alerta)
    db.flush()
    return alerta
