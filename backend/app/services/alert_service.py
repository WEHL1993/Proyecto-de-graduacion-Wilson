"""Consulta de la bandeja de alertas."""

from sqlalchemy.orm import Session

from app.domain.enums import EstadoAlerta
from app.repositories import alert_repo
from app.schemas.alerts import AlertItem, AlertList


def listar(db: Session, *, estado: EstadoAlerta | None, limite: int) -> AlertList:
    filas, total = alert_repo.listar(db, estado=estado, limite=limite)
    return AlertList(
        total=total,
        alertas=[
            AlertItem(
                id=a.id,
                tipo=a.tipo,
                severidad=a.severidad,
                mensaje=a.mensaje,
                estado=a.estado,
                producto_id=a.producto_id,
                modelo_id=a.modelo_id,
                creada_en=a.creada_en,
            )
            for a in filas
        ],
    )
