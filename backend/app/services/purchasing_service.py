"""Caso de uso: abastecimiento y pedidos a proveedor.

Sugerencia: `cantidad_a_pedir = max(0, (demanda_proyectada + stock_minimo) - stock_actual)`, con
la demanda agregada (todas las rutas) de los próximos N días del modelo en producción.

Estados: `borrador → enviado → confirmado → recibido` (más `cancelado` desde borrador/enviado).
  - enviar:    EncargadoCompras (`pedido_proveedor:gestionar`).
  - confirmar: el Proveedor (`pedido_proveedor:confirmar`), solo sobre sus propios pedidos.
  - recibir:   EncargadoBodega/EncargadoInventario (`inventario:ajustar`):
               entrada en kardex + `stock_actual`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoPedido, NombreRol, ReferenciaTipo
from app.domain.models.operations import PedidoProveedor, RecepcionMercaderia
from app.repositories import catalog_repo, purchasing_repo, user_repo
from app.schemas.auth import UsuarioAutenticado
from app.schemas.predictions import DemandRequest
from app.schemas.purchasing import (
    PedidoConfirmacion,
    PedidoCreate,
    PedidoItemOut,
    PedidoOut,
    PedidoPage,
    RecepcionCreate,
    RecepcionOut,
    SugerenciaCompra,
    SugerenciasResponse,
)
from app.services import inventory_service, prediction_service
from app.services.bitacora_service import auditar

_CENTESIMA = Decimal("0.01")
_CERO = Decimal("0.00")
_MAX_PRODUCTOS_POR_PREDICCION = 200


# ------------------------------------------------------------------ sugerencias
def calcular_cantidad_a_pedir(
    demanda_proyectada: Decimal, stock_minimo: Decimal, stock_actual: Decimal
) -> Decimal:
    """Paquetes enteros a pedir: una fracción de paquete no se puede comprar, se redondea hacia arriba."""
    faltante = max(_CERO, (demanda_proyectada + stock_minimo) - stock_actual)
    return faltante.to_integral_value(rounding=ROUND_CEILING).quantize(_CENTESIMA)


@auditar
def sugerir(db: Session, horizonte_dias: int) -> SugerenciasResponse:
    candidatos = purchasing_repo.productos_reabastecibles(db)
    demanda, advertencias = _demanda_proyectada(
        db, [p.id for p, _, _ in candidatos], horizonte_dias
    )

    sugerencias: list[SugerenciaCompra] = []
    for producto, proveedor, inv in candidatos:
        actual = inv.stock_actual if inv else _CERO
        proyectada = demanda.get(producto.id)
        cantidad = calcular_cantidad_a_pedir(proyectada or _CERO, producto.stock_minimo, actual)
        if cantidad <= 0:
            continue
        sugerencias.append(
            SugerenciaCompra(
                producto_id=producto.id,
                sku=producto.sku,
                nombre=producto.nombre,
                proveedor_id=proveedor.id,
                proveedor_nombre=proveedor.nombre,
                lead_time_dias=proveedor.lead_time_dias,
                stock_actual=actual,
                stock_minimo=producto.stock_minimo,
                demanda_proyectada=proyectada or _CERO,
                cantidad_sugerida=cantidad,
                costo_unitario=producto.costo_unitario,
                pronostico_disponible=proyectada is not None,
            )
        )
    return SugerenciasResponse(
        horizonte_dias=horizonte_dias,
        generado_en=datetime.now(UTC),
        sugerencias=sugerencias,
        advertencias=advertencias,
    )


def _demanda_proyectada(
    db: Session, producto_ids: list[uuid.UUID], horizonte_dias: int
) -> tuple[dict[uuid.UUID, Decimal], list[str]]:
    """Demanda agregada por producto en el horizonte. Los productos sin pronóstico no aparecen
    en el resultado (se sugiere solo por punto de reorden) y se avisa en `advertencias`."""
    demanda: dict[uuid.UUID, Decimal] = {}
    for i in range(0, len(producto_ids), _MAX_PRODUCTOS_POR_PREDICCION):
        lote = producto_ids[i : i + _MAX_PRODUCTOS_POR_PREDICCION]
        try:
            demanda.update(_predecir_lote(db, lote, horizonte_dias))
        except AppError as exc:
            if exc.codigo == "SIN_MODELO_PRODUCTIVO":
                return {}, [
                    "No hay modelo en producción: las sugerencias usan solo el punto de reorden."
                ]
            if exc.codigo != "HISTORIAL_INSUFICIENTE":
                raise
            sin_historia = {uuid.UUID(p) for p in (exc.detalle or {}).get("producto_ids", [])}
            con_historia = [p for p in lote if p not in sin_historia]
            if con_historia:
                demanda.update(_predecir_lote(db, con_historia, horizonte_dias))
    advertencias: list[str] = []
    sin_pronostico = len(set(producto_ids) - set(demanda))
    if sin_pronostico:
        advertencias.append(
            f"{sin_pronostico} producto(s) sin historial suficiente: se sugiere solo por punto "
            "de reorden."
        )
    return demanda, advertencias


def _predecir_lote(
    db: Session, producto_ids: list[uuid.UUID], horizonte_dias: int
) -> dict[uuid.UUID, Decimal]:
    respuesta = prediction_service.predecir_demanda(
        db,
        DemandRequest(
            producto_ids=producto_ids,
            fecha_base=date.today(),
            horizonte_dias=horizonte_dias,
            incluir_intervalo=False,
        ),
    )
    return {
        pron.producto_id: sum(
            (max(Decimal(0), Decimal(str(p.demanda_predicha))) for p in pron.serie), Decimal(0)
        ).to_integral_value(rounding=ROUND_HALF_UP).quantize(_CENTESIMA)
        for pron in respuesta.pronosticos
    }


# ------------------------------------------------------------------ crear
@auditar
def crear_pedido(db: Session, solicitud: PedidoCreate, usuario_id: uuid.UUID) -> PedidoOut:
    proveedor = purchasing_repo.obtener_proveedor(db, solicitud.proveedor_id)
    if proveedor is None or not proveedor.activo:
        raise AppError("PROVEEDOR_NO_ENCONTRADO", "El proveedor no existe o está inactivo.")

    hoy = date.today()
    if solicitud.fecha_esperada is not None and solicitud.fecha_esperada < hoy:
        raise AppError("FECHA_ESPERADA_INVALIDA", "La fecha esperada no puede ser anterior a hoy.")

    pedidos_ids = {i.producto_id for i in solicitud.items}
    productos = purchasing_repo.productos_de(db, pedidos_ids)
    faltantes = pedidos_ids - set(productos)
    if faltantes:
        raise AppError(
            "PRODUCTO_NO_ENCONTRADO",
            "Uno o más productos no existen en el catálogo.",
            detalle={"producto_ids": sorted(str(p) for p in faltantes)},
        )
    ajenos = [str(p.id) for p in productos.values() if p.proveedor_id != proveedor.id]
    if ajenos:
        raise AppError(
            "PRODUCTO_AJENO_A_PROVEEDOR",
            "Hay productos que no son suministrados por el proveedor indicado.",
            detalle={"producto_ids": sorted(ajenos)},
        )

    detalles = [
        {
            "producto_id": i.producto_id,
            "alerta_origen_id": i.alerta_origen_id,
            "cantidad": i.cantidad,
            "costo_unitario": (
                i.costo_unitario
                if i.costo_unitario is not None
                else productos[i.producto_id].costo_unitario
            ),
        }
        for i in solicitud.items
    ]
    total = sum((d["cantidad"] * d["costo_unitario"] for d in detalles), Decimal(0))
    pedido = purchasing_repo.crear(
        db,
        cabecera={
            "proveedor_id": proveedor.id,
            "creado_por": usuario_id,
            "estado": EstadoPedido.ENVIADO if solicitud.enviar else EstadoPedido.BORRADOR,
            "fecha_pedido": hoy,
            "fecha_esperada": solicitud.fecha_esperada,
            "total": total.quantize(_CENTESIMA),
        },
        detalles=detalles,
    )
    db.commit()
    return _salida(db, [pedido])[0]


# ------------------------------------------------------------------ consulta
@auditar
def listar(
    db: Session,
    usuario: UsuarioAutenticado,
    *,
    estado: EstadoPedido | None,
    limit: int,
    offset: int,
) -> PedidoPage:
    pedidos, total = purchasing_repo.listar(
        db, proveedor_id=_alcance(db, usuario), estado=estado, limit=limit, offset=offset
    )
    return PedidoPage(items=_salida(db, pedidos), total=total, limit=limit, offset=offset)


@auditar
def obtener(db: Session, usuario: UsuarioAutenticado, pedido_id: uuid.UUID) -> PedidoOut:
    proveedor_id = _alcance(db, usuario)
    pedido = purchasing_repo.obtener(db, pedido_id)
    # 404 (no 403) ante un pedido ajeno: no revela su existencia (TC-RBAC-03).
    if pedido is None or (proveedor_id is not None and pedido.proveedor_id != proveedor_id):
        raise _no_encontrado()
    return _salida(db, [pedido])[0]


# ------------------------------------------------------------------ transiciones
@auditar
def enviar(db: Session, pedido_id: uuid.UUID) -> PedidoOut:
    """`borrador → enviado`: EncargadoCompras aprueba y envía la orden."""
    pedido = _bloquear(db, pedido_id, (EstadoPedido.BORRADOR,), "enviar")
    pedido.estado = EstadoPedido.ENVIADO
    db.commit()
    return _salida(db, [pedido])[0]


@auditar
def cancelar(db: Session, pedido_id: uuid.UUID) -> PedidoOut:
    pedido = _bloquear(db, pedido_id, (EstadoPedido.BORRADOR, EstadoPedido.ENVIADO), "cancelar")
    pedido.estado = EstadoPedido.CANCELADO
    db.commit()
    return _salida(db, [pedido])[0]


@auditar
def confirmar(
    db: Session, usuario: UsuarioAutenticado, pedido_id: uuid.UUID, solicitud: PedidoConfirmacion
) -> PedidoOut:
    """`enviado → confirmado`: el proveedor confirma recepción y fecha estimada."""
    proveedor_id = _proveedor_del_usuario(db, usuario)
    pedido = _bloquear(db, pedido_id, (EstadoPedido.ENVIADO,), "confirmar", proveedor_id)
    if solicitud.fecha_esperada < pedido.fecha_pedido:
        raise AppError(
            "FECHA_ESPERADA_INVALIDA", "La fecha esperada no puede ser anterior a la del pedido."
        )
    pedido.fecha_esperada = solicitud.fecha_esperada
    pedido.estado = EstadoPedido.CONFIRMADO
    db.commit()
    return _salida(db, [pedido])[0]


@auditar
def recibir(db: Session, pedido_id: uuid.UUID, usuario_id: uuid.UUID) -> PedidoOut:
    """`confirmado → recibido`: EncargadoBodega valida el ingreso físico. Registra la entrada en
    `kardex` e incrementa `stock_actual`, todo atómico con el cambio de estado."""
    pedido = _bloquear(db, pedido_id, (EstadoPedido.CONFIRMADO,), "recibir")
    inventory_service.registrar_entrada(
        db,
        {d.producto_id: d.cantidad for d in pedido.detalles},
        referencia_tipo=ReferenciaTipo.PEDIDO,
        referencia_id=pedido.id,
        usuario_id=usuario_id,
    )
    pedido.estado = EstadoPedido.RECIBIDO
    db.commit()
    return _salida(db, [pedido])[0]


# ------------------------------------------------------------------ utilidades
def _proveedor_del_usuario(db: Session, usuario: UsuarioAutenticado) -> uuid.UUID | None:
    """Proveedor al que está atado el usuario. `None` solo para Administrador (sin restricción)."""
    proveedor_id = user_repo.proveedor_id_de(db, usuario.id)
    if (
        proveedor_id is None and NombreRol.ADMINISTRADOR not in usuario.roles
    ):  # TODO: migrar a permiso
        raise AppError(
            "PROVEEDOR_NO_ASOCIADO",
            "Su usuario no está asociado a un proveedor.",
            status_code=403,
        )
    return proveedor_id


def _alcance(db: Session, usuario: UsuarioAutenticado) -> uuid.UUID | None:
    """EncargadoCompras y EncargadoBodega (que recibe) ven todos los pedidos; el Proveedor,
    solo los suyos."""
    if {"pedido_proveedor:gestionar", "inventario:ajustar"} & set(usuario.permisos):
        return None
    return _proveedor_del_usuario(db, usuario)


def _no_encontrado() -> AppError:
    return AppError("PEDIDO_NO_ENCONTRADO", "El pedido indicado no existe.", status_code=404)


def _bloquear(
    db: Session,
    pedido_id: uuid.UUID,
    estados_validos: tuple[EstadoPedido, ...],
    accion: str,
    proveedor_id: uuid.UUID | None = None,
) -> PedidoProveedor:
    pedido = purchasing_repo.obtener(db, pedido_id, bloquear=True)
    if pedido is None or (proveedor_id is not None and pedido.proveedor_id != proveedor_id):
        raise _no_encontrado()
    if pedido.estado not in estados_validos:
        raise AppError(
            "ESTADO_PEDIDO_INVALIDO",
            f"No se puede {accion} un pedido en estado `{pedido.estado}`.",
            detalle={"estado": pedido.estado, "estados_validos": [str(e) for e in estados_validos]},
        )
    return pedido


def _salida(db: Session, pedidos: Sequence[PedidoProveedor]) -> list[PedidoOut]:
    catalogo = catalog_repo.productos_resumen(
        db, [d.producto_id for p in pedidos for d in p.detalles]
    )
    proveedores = purchasing_repo.nombres_proveedores(db, {p.proveedor_id for p in pedidos})
    return [
        PedidoOut(
            id=p.id,
            proveedor_id=p.proveedor_id,
            proveedor_nombre=proveedores.get(p.proveedor_id, ""),
            estado=EstadoPedido(p.estado),
            fecha_pedido=p.fecha_pedido,
            fecha_esperada=p.fecha_esperada,
            total=p.total,
            creado_por=p.creado_por,
            items=[
                PedidoItemOut(
                    producto_id=d.producto_id,
                    sku=catalogo[d.producto_id][0],
                    producto_nombre=catalogo[d.producto_id][1],
                    cantidad=d.cantidad,
                    costo_unitario=d.costo_unitario,
                    subtotal=(d.cantidad * d.costo_unitario).quantize(_CENTESIMA),
                )
                for d in sorted(p.detalles, key=lambda d: catalogo[d.producto_id][0])
            ],
        )
        for p in pedidos
    ]


@auditar
def registrar_recepcion(
    db: Session, solicitud: RecepcionCreate, usuario_id: uuid.UUID
) -> RecepcionOut:
    """Ingreso físico con documento: existencias, kardex y pedido se confirman juntos.

    Una recepción cierra el pedido; cualquier diferencia (faltante o excedente) se conserva
    como recibido_parcial. Los ceros se documentan, pero no generan movimientos vacíos.
    """
    # Serializa entregas del mismo pedido antes de comprobar factura y estado.
    if solicitud.pedido_id:
        purchasing_repo.obtener(db, solicitud.pedido_id, bloquear=True)
    duplicada = db.scalar(
        select(RecepcionMercaderia.id)
        .where(
            or_(
                RecepcionMercaderia.numero_autorizacion == solicitud.numero_autorizacion,
                (RecepcionMercaderia.serie == solicitud.serie)
                & (RecepcionMercaderia.numero == solicitud.numero),
            )
        )
        .limit(1)
    )
    if duplicada:
        raise _factura_duplicada()
    pedido = (
        _bloquear(db, solicitud.pedido_id, (EstadoPedido.CONFIRMADO,), "recibir")
        if solicitud.pedido_id
        else None
    )
    ids = {i.producto_id for i in solicitud.items}
    productos = purchasing_repo.productos_de(db, ids)
    if ids != set(productos) or any(not p.activo for p in productos.values()):
        raise AppError("PRODUCTO_INVALIDO", "Hay productos inexistentes o inactivos.")
    if pedido and ids != {d.producto_id for d in pedido.detalles}:
        raise AppError(
            "DETALLE_RECEPCION_INVALIDO", "Incluya exactamente los productos del pedido."
        )
    cantidades = {i.producto_id: i.cantidad_recibida for i in solicitud.items}
    recepcion = RecepcionMercaderia(
        pedido_id=solicitud.pedido_id,
        usuario_id=usuario_id,
        **solicitud.model_dump(exclude={"pedido_id", "items"}),
        items=[i.model_dump(mode="json") for i in solicitud.items],
    )
    try:
        # UNIQUE es la garantía final ante solicitudes concurrentes. El savepoint deja
        # la sesión utilizable al traducir el conflicto, sin entradas ni stock nuevos.
        with db.begin_nested():
            db.add(recepcion)
            db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "pgcode", None) == "23505" and getattr(
            getattr(exc.orig, "diag", None), "constraint_name", None
        ) in {"uq_recepciones_autorizacion", "uq_recepciones_serie_numero"}:
            raise _factura_duplicada() from exc
        raise
    inventory_service.registrar_entrada(
        db,
        cantidades,
        referencia_tipo=ReferenciaTipo.RECEPCION,
        referencia_id=recepcion.id,
        usuario_id=usuario_id,
        motivo=f"FEL {recepcion.serie}-{recepcion.numero} / {recepcion.numero_autorizacion}",
    )
    if pedido:
        pedido.estado = (
            EstadoPedido.RECIBIDO
            if all(cantidades[d.producto_id] == d.cantidad for d in pedido.detalles)
            else EstadoPedido.RECIBIDO_PARCIAL
        )
    db.commit()
    return RecepcionOut(
        id=recepcion.id,
        pedido_id=recepcion.pedido_id,
        **solicitud.model_dump(exclude={"pedido_id", "items"}),
        estado_pedido=pedido.estado if pedido else None,
        items=solicitud.items,
    )


def _factura_duplicada() -> AppError:
    return AppError(
        "FACTURA_DUPLICADA",
        "La factura ya fue registrada: el UUID de autorización "
        "o la serie y número están duplicados.",
        status_code=409,
    )
