"""Bandeja de alertas: listado y reconocimiento, con visibilidad según los permisos del usuario."""

import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoAlerta, TipoAlerta
from app.domain.models.ml import Alerta
from app.repositories import alert_repo
from app.schemas.alerts import AlertItem, AlertList
from app.schemas.auth import UsuarioAutenticado
from app.services.bitacora_service import auditar

# Cada tipo de alerta lo ven quienes tienen algún permiso de su dominio (matriz 1.4), de modo
# que Bodega no ve el MAPE ni Gerente los errores de ETL. Admin tiene todos los permisos.
PERMISOS_POR_TIPO: dict[TipoAlerta, frozenset[str]] = {
    TipoAlerta.STOCK_BAJO: frozenset({"inventario:leer", "inventario:ajustar"}),
    TipoAlerta.QUIEBRE_PROYECTADO: frozenset(
        {"prediccion:consultar", "pedido_proveedor:gestionar"}
    ),
    TipoAlerta.MAPE_UMBRAL: frozenset({"ml:metricas:leer", "ml:reentrenar"}),
    TipoAlerta.ETL_ERROR: frozenset({"etl:cargar"}),
    TipoAlerta.DIFERENCIA_CAJA: frozenset({"liquidaciones:leer"}),
}


def tipos_visibles(usuario: UsuarioAutenticado) -> list[TipoAlerta]:
    permisos = set(usuario.permisos)
    return [tipo for tipo, requeridos in PERMISOS_POR_TIPO.items() if permisos & requeridos]


def _a_dto(a: Alerta) -> AlertItem:
    return AlertItem(
        id=a.id,
        tipo=a.tipo,
        severidad=a.severidad,
        mensaje=a.mensaje,
        estado=a.estado,
        producto_id=a.producto_id,
        modelo_id=a.modelo_id,
        creada_en=a.creada_en,
    )


@auditar
def listar(
    db: Session, usuario: UsuarioAutenticado, *, estado: EstadoAlerta | None, limite: int
) -> AlertList:
    tipos = tipos_visibles(usuario)
    if not tipos:
        return AlertList(total=0, alertas=[])
    filas, total = alert_repo.listar(db, estado=estado, limite=limite, tipos=tipos)
    return AlertList(total=total, alertas=[_a_dto(a) for a in filas])


@auditar
def reconocer(db: Session, usuario: UsuarioAutenticado, alerta_id: uuid.UUID) -> AlertItem:
    alerta = alert_repo.obtener(db, alerta_id)
    # 404 (no 403) para tipos ajenos: no se revela la existencia de alertas fuera del rol.
    if alerta is None or alerta.tipo not in tipos_visibles(usuario):
        raise AppError("ALERTA_NO_ENCONTRADA", "La alerta no existe.", status_code=404)
    if alerta.estado != EstadoAlerta.ABIERTA:
        raise AppError(
            "ALERTA_NO_ABIERTA",
            f"Solo se reconocen alertas abiertas (estado actual: {alerta.estado}).",
            status_code=409,
        )
    alert_repo.reconocer(alerta)
    db.commit()
    return _a_dto(alerta)
