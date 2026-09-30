"""Casos de uso de inventario: disponibilidad, movimientos de kardex y alertas de cobertura.

`stock_disponible = stock_actual - stock_reservado`. Convención de `kardex.saldo_resultante`:
es el `stock_actual` físico tras el movimiento (las reservas y liberaciones no lo alteran).

Las operaciones que mutan (`reservar`, `liberar`, `confirmar_salida`) solo hacen `flush`: el
commit lo decide el caso de uso que las orquesta, para que reserva + estado sean atómicos.
"""

import uuid
from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import ReferenciaTipo, Severidad, TipoAlerta, TipoMovimiento
from app.domain.models.catalog import Inventario
from app.repositories import alert_repo, inventory_repo
from app.schemas.inventory import KardexEntry, KardexPage, StockItem, StockPage

CERO = Decimal("0.00")


# ------------------------------------------------------------------ consulta
def stock_disponible(db: Session, producto_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Stock disponible por producto; un producto sin fila de inventario cuenta como 0."""
    existencias = inventory_repo.obtener_por_productos(db, producto_ids)
    return {
        pid: existencias[pid].stock_disponible if pid in existencias else CERO
        for pid in producto_ids
    }


def listar_existencias(
    db: Session,
    *,
    producto_id: uuid.UUID | None,
    solo_bajo_minimo: bool,
    limit: int,
    offset: int,
) -> StockPage:
    filas, total = inventory_repo.listar_existencias(
        db,
        producto_id=producto_id,
        solo_bajo_minimo=solo_bajo_minimo,
        limit=limit,
        offset=offset,
    )
    items = []
    for producto, inv in filas:
        actual = inv.stock_actual if inv else CERO
        reservado = inv.stock_reservado if inv else CERO
        disponible = actual - reservado
        items.append(
            StockItem(
                producto_id=producto.id,
                sku=producto.sku,
                nombre=producto.nombre,
                stock_actual=actual,
                stock_reservado=reservado,
                stock_disponible=disponible,
                stock_minimo=producto.stock_minimo,
                bajo_minimo=disponible < producto.stock_minimo,
            )
        )
    return StockPage(items=items, total=total, limit=limit, offset=offset)


def listar_kardex(db: Session, **filtros) -> KardexPage:
    movimientos, total = inventory_repo.listar_kardex(db, **filtros)
    return KardexPage(
        items=[KardexEntry.model_validate(m, from_attributes=True) for m in movimientos],
        total=total,
        limit=filtros["limit"],
        offset=filtros["offset"],
    )


# ------------------------------------------------------------------ movimientos
def reservar(
    db: Session,
    cantidades: Mapping[uuid.UUID, Decimal],
    *,
    referencia_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """Reserva stock (bloqueando las filas). `CANTIDAD_EXCEDE_STOCK` si algún producto no
    tiene disponible suficiente; en ese caso no se modifica nada."""
    positivas = {pid: q for pid, q in cantidades.items() if q > 0}
    existencias = inventory_repo.obtener_por_productos(db, positivas, bloquear=True)
    excedidos = {
        str(pid): {"solicitada": str(q), "disponible": str(_disponible(existencias, pid))}
        for pid, q in positivas.items()
        if q > _disponible(existencias, pid)
    }
    if excedidos:
        raise AppError(
            "CANTIDAD_EXCEDE_STOCK",
            "La cantidad a reservar excede el stock disponible.",
            detalle={"productos": excedidos},
        )
    for pid, cantidad in positivas.items():
        inv = existencias[pid]
        inv.stock_reservado += cantidad
        _mover(db, inv, TipoMovimiento.RESERVA, cantidad, referencia_id, usuario_id)


def liberar(
    db: Session,
    cantidades: Mapping[uuid.UUID, Decimal],
    *,
    referencia_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """Libera reservas (nunca por debajo de 0)."""
    positivas = {pid: q for pid, q in cantidades.items() if q > 0}
    existencias = inventory_repo.obtener_por_productos(db, positivas, bloquear=True)
    for pid, cantidad in positivas.items():
        inv = existencias.get(pid)
        if inv is None:
            continue
        liberada = min(cantidad, inv.stock_reservado)
        if liberada <= 0:
            continue
        inv.stock_reservado -= liberada
        _mover(db, inv, TipoMovimiento.LIBERACION, liberada, referencia_id, usuario_id)


def confirmar_salida(
    db: Session,
    cantidades: Mapping[uuid.UUID, Decimal],
    *,
    referencia_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """Salida física (despacho): consume la reserva y descuenta `stock_actual`."""
    positivas = {pid: q for pid, q in cantidades.items() if q > 0}
    existencias = inventory_repo.obtener_por_productos(db, positivas, bloquear=True)
    insuficientes = {
        str(pid): str(q)
        for pid, q in positivas.items()
        if pid not in existencias or q > existencias[pid].stock_actual
    }
    if insuficientes:
        raise AppError(
            "STOCK_INSUFICIENTE",
            "La existencia física no alcanza para la salida.",
            detalle={"productos": insuficientes},
        )
    for pid, cantidad in positivas.items():
        inv = existencias[pid]
        inv.stock_actual -= cantidad
        inv.stock_reservado = max(CERO, inv.stock_reservado - cantidad)
        _mover(db, inv, TipoMovimiento.SALIDA, cantidad, referencia_id, usuario_id)


def _disponible(existencias: Mapping[uuid.UUID, Inventario], pid: uuid.UUID) -> Decimal:
    return existencias[pid].stock_disponible if pid in existencias else CERO


def _mover(
    db: Session,
    inv: Inventario,
    tipo: TipoMovimiento,
    cantidad: Decimal,
    referencia_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    db.flush()  # que la CHECK de `inventario` falle aquí y no en el commit
    inventory_repo.registrar_movimiento(
        db,
        producto_id=inv.producto_id,
        tipo=tipo,
        cantidad=cantidad,
        saldo_resultante=inv.stock_actual,
        referencia_tipo=ReferenciaTipo.CARGA_RUTA,
        referencia_id=referencia_id,
        usuario_id=usuario_id,
    )


# ------------------------------------------------------------------ alertas
def evaluar_cobertura(
    db: Session,
    cobertura: Mapping[uuid.UUID, tuple[Decimal, Decimal]],
    *,
    modelo_id: uuid.UUID,
    contexto: str,
) -> list[uuid.UUID]:
    """Alerta cuando el stock disponible no cubre la demanda predicha.

    `cobertura`: `producto_id -> (demanda_predicha, stock_disponible)`. Sin disponible y con
    demanda → `quiebre_proyectado` (crítica); con disponible parcial → `stock_bajo`
    (advertencia). No duplica una alerta abierta del mismo tipo y producto. Devuelve los ids
    de las alertas nuevas.
    """
    nuevas: list[uuid.UUID] = []
    for pid, (demanda, disponible) in cobertura.items():
        if demanda <= disponible:
            continue
        if disponible <= 0:
            tipo, severidad = TipoAlerta.QUIEBRE_PROYECTADO, Severidad.CRITICA
            mensaje = f"Sin stock disponible para la demanda proyectada de {demanda} ({contexto})."
        else:
            tipo, severidad = TipoAlerta.STOCK_BAJO, Severidad.ADVERTENCIA
            mensaje = (
                f"Stock disponible {disponible} inferior a la demanda proyectada {demanda} "
                f"({contexto})."
            )
        if alert_repo.abierta_de_producto(db, tipo=tipo, producto_id=pid) is not None:
            continue
        alerta = alert_repo.crear(
            db,
            tipo=tipo,
            severidad=severidad,
            mensaje=mensaje,
            producto_id=pid,
            modelo_id=modelo_id,
        )
        nuevas.append(alerta.id)
    return nuevas
