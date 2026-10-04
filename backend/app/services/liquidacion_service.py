"""Caso de uso: liquidación diaria de ventas, unidades y dinero (ADR-14).

El admin liquida cada día por ruta y vendedor. Un **borrador** puede guardarse incompleto y no
afecta al modelo. **Cerrar** (acción explícita) valida los cuadres de unidades y dinero y, en una
única transacción: crea un lote `origen=liquidacion`, escribe `ventas_historicas` (UPSERT por la
restricción única) y sus comisiones, rellena `demanda_real` de los pronósticos de esa
fecha/ruta/producto, calcula el cuadre de caja (alerta `diferencia_caja` sobre el umbral), encola
`evaluate_production` y audita. Nunca despacha ni toca el stock (ADR-06): las devoluciones se
muestran como «devolución esperada» para el flujo de inventario.

Las validaciones puras (sin BD) viven arriba y se prueban en `tests/unit`.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import parametros
from app.core.errors import AppError
from app.domain.enums import EstadoLiquidacion, Severidad, TipoAlerta, TipoJob
from app.domain.models.catalog import Ruta
from app.domain.models.sales import LiquidacionDiaria
from app.repositories import (
    alert_repo,
    carga_repo,
    catalog_repo,
    forecast_repo,
    job_repo,
    liquidacion_repo,
    parametro_repo,
    sales_repo,
    user_repo,
)
from app.repositories.catalog_repo import ProductoLiquidable
from app.schemas.liquidacion import (
    CorreccionRequest,
    CuadreDinero,
    CuadreUnidades,
    LineaPrecarga,
    LineaRespuesta,
    LiquidacionConfig,
    LiquidacionRequest,
    LiquidacionResponse,
    LiquidacionResumen,
    ListadoLiquidaciones,
    PagosLiquidacion,
    PrecargaResponse,
)
from app.services import etl_service
from app.services.bitacora_service import auditar

auditoria = logging.getLogger("app.auditoria")

_CENTAVOS = Decimal("0.01")
_CERO = Decimal(0)


# ====================================================================== lógica pura (sin BD)
@dataclass(frozen=True)
class LineaCalculada:
    producto_id: uuid.UUID
    cargada: Decimal
    vendida: Decimal
    devuelta: Decimal
    merma: Decimal
    precio: Decimal
    agotado: bool = False
    justificacion: str | None = None

    @property
    def monto(self) -> Decimal:
        return calcular_monto(self.vendida, self.precio)

    @property
    def diferencia(self) -> Decimal:
        """Unidades sin justificar: cargada − vendida − devuelta − merma (0 = cuadra)."""
        return self.cargada - self.vendida - self.devuelta - self.merma


def calcular_monto(vendida: Decimal, precio: Decimal) -> Decimal:
    """`monto = cantidad vendida × precio`, a centavos (numeric(14,2))."""
    return (vendida * precio).quantize(_CENTAVOS, ROUND_HALF_UP)


def validar_fecha(fecha: date, hoy: date | None = None) -> None:
    if fecha > (hoy or date.today()):
        raise AppError("VENTA_FECHA_FUTURA", "No se puede liquidar una fecha futura.")


def validar_productos_unicos(producto_ids: Sequence[uuid.UUID]) -> None:
    vistos: set[uuid.UUID] = set()
    repetidos = sorted({str(p) for p in producto_ids if p in vistos or vistos.add(p)})
    if repetidos:
        raise AppError(
            "PRODUCTO_DUPLICADO_EN_CIERRE",
            "Un producto no puede repetirse en la liquidación.",
            detalle={"producto_ids": repetidos},
        )


def validar_hay_movimiento(lineas: Sequence[LineaCalculada]) -> None:
    if not any(ln.vendida > 0 or ln.cargada > 0 for ln in lineas):
        raise AppError(
            "LIQUIDACION_SIN_MOVIMIENTO",
            "La liquidación debe tener al menos una línea con unidades cargadas o vendidas.",
        )


def _detalle_unidades(
    lineas: Sequence[LineaCalculada], etiquetas: Mapping[uuid.UUID, str] | None
) -> dict[str, dict[str, str]]:
    return {
        (etiquetas or {}).get(ln.producto_id, str(ln.producto_id)): {
            "cargada": str(ln.cargada),
            "vendida": str(ln.vendida),
            "devuelta": str(ln.devuelta),
            "merma": str(ln.merma),
            "diferencia": str(ln.diferencia),
        }
        for ln in lineas
    }


def validar_unidades_no_exceden(
    lineas: Sequence[LineaCalculada], etiquetas: Mapping[uuid.UUID, str] | None = None
) -> None:
    """Vendida + devuelta + merma nunca puede superar lo cargado (también lo blinda un CHECK)."""
    excedidas = [ln for ln in lineas if ln.diferencia < 0]
    if excedidas:
        raise AppError(
            "UNIDADES_NO_CUADRAN",
            "Vendido + devuelto + merma excede lo cargado.",
            detalle={"productos": _detalle_unidades(excedidas, etiquetas)},
        )


def exigir_unidades_cuadran(
    lineas: Sequence[LineaCalculada], etiquetas: Mapping[uuid.UUID, str] | None = None
) -> None:
    """Para cerrar: cargada = vendida + devuelta + merma en cada presentación."""
    sin_cuadrar = [ln for ln in lineas if ln.diferencia != 0]
    if sin_cuadrar:
        raise AppError(
            "UNIDADES_NO_CUADRAN",
            "Las unidades no cuadran: cargada debe ser igual a vendida + devuelta + merma.",
            detalle={"productos": _detalle_unidades(sin_cuadrar, etiquetas)},
        )


def total_venta(lineas: Sequence[LineaCalculada]) -> Decimal:
    return sum((ln.monto for ln in lineas), _CERO)


def total_pagos(pagos: PagosLiquidacion) -> Decimal:
    return pagos.efectivo + pagos.transferencia + pagos.credito


def calcular_caja(pagos: PagosLiquidacion) -> tuple[Decimal, Decimal]:
    """`(efectivo_esperado, diferencia_caja)`: esperado = efectivo + cobro de saldos − gastos;
    diferencia = entregado − esperado (negativa = falta dinero)."""
    esperado = pagos.efectivo + pagos.cobro_saldos - pagos.gastos
    return esperado, pagos.efectivo_entregado - esperado


def exigir_montos_cuadran(venta: Decimal, pagos: PagosLiquidacion) -> None:
    """Para cerrar: la venta debe igualar efectivo + transferencia + crédito."""
    diferencia = venta - total_pagos(pagos)
    if diferencia != 0:
        raise AppError(
            "MONTOS_NO_CUADRAN",
            "La venta total no coincide con efectivo + transferencia + crédito.",
            detalle={
                "venta_total": str(venta),
                "total_pagos": str(total_pagos(pagos)),
                "diferencia": str(diferencia),
            },
        )


def supera_umbral(diferencia_caja: Decimal, umbral: Decimal) -> bool:
    return abs(diferencia_caja) > umbral


def calcular_checksum(
    fecha: date,
    ruta_id: uuid.UUID,
    vendedor_id: uuid.UUID,
    lineas: Sequence[LineaCalculada],
) -> str:
    """SHA-256 determinista de `(fecha, ruta, vendedor, líneas ordenadas por producto)`."""
    cuerpo = {
        "fecha": fecha.isoformat(),
        "ruta_id": str(ruta_id),
        "vendedor_id": str(vendedor_id),
        "lineas": [
            [
                str(ln.producto_id),
                str(ln.cargada.quantize(_CENTAVOS)),
                str(ln.vendida.quantize(_CENTAVOS)),
                str(ln.devuelta.quantize(_CENTAVOS)),
                str(ln.merma.quantize(_CENTAVOS)),
                str(ln.precio.quantize(_CENTAVOS)),
                ln.agotado,
            ]
            for ln in sorted(lineas, key=lambda x: str(x.producto_id))
        ],
    }
    return hashlib.sha256(json.dumps(cuerpo, separators=(",", ":")).encode()).hexdigest()


def checksum_anulado(checksum: str, liquidacion_id: uuid.UUID, version: int) -> str:
    """Re-sella el checksum de un lote anulado para liberar el original (`unique`)."""
    return hashlib.sha256(f"{checksum}:anulado:{liquidacion_id}:{version}".encode()).hexdigest()


# ====================================================================== preparación (con BD)
@dataclass
class _Preparada:
    ruta: Ruta
    vendedor_id: uuid.UUID
    lineas: list[LineaCalculada]
    catalogo: dict[uuid.UUID, ProductoLiquidable]
    advertencias: list[str]


def _preparar(db: Session, solicitud: LiquidacionRequest, *, hoy: date | None = None) -> _Preparada:
    """Valida la solicitud contra reglas de negocio y catálogo; devuelve las líneas calculadas."""
    validar_fecha(solicitud.fecha, hoy)
    ruta = catalog_repo.obtener_ruta(db, solicitud.ruta_id)
    if ruta is None:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta indicada no existe.")
    if not ruta.activa:
        raise AppError("RUTA_INACTIVA", "La ruta indicada está inactiva.")

    vendedor_id = solicitud.vendedor_id or ruta.vendedor_id
    if vendedor_id is None:
        raise AppError(
            "VENDEDOR_NO_DEFINIDO", "La ruta no tiene vendedor asignado; indique `vendedor_id`."
        )
    vendedor = user_repo.obtener_por_id(db, vendedor_id)
    if vendedor is None:
        raise AppError("VENDEDOR_NO_ENCONTRADO", "El vendedor indicado no existe.")
    if not vendedor.activo:
        raise AppError("VENDEDOR_INACTIVO", "El vendedor indicado está inactivo.")

    producto_ids = [ln.producto_id for ln in solicitud.lineas]
    validar_productos_unicos(producto_ids)
    catalogo = catalog_repo.productos_para_liquidacion(db, producto_ids)
    inexistentes = sorted(str(p) for p in set(producto_ids) - set(catalogo))
    if inexistentes:
        raise AppError(
            "PRODUCTO_NO_ENCONTRADO",
            "Uno o más productos no existen en el catálogo.",
            detalle={"producto_ids": inexistentes},
        )
    inactivos = sorted(c.sku for c in catalogo.values() if not c.activo)
    if inactivos:
        raise AppError(
            "PRODUCTO_INACTIVO",
            "Uno o más productos están inactivos.",
            detalle={"skus": inactivos},
        )

    lineas = [
        LineaCalculada(
            producto_id=ln.producto_id,
            cargada=ln.cantidad_cargada,
            vendida=ln.cantidad_vendida,
            devuelta=ln.cantidad_devuelta,
            merma=ln.cantidad_merma,
            precio=(
                ln.precio_unitario
                if ln.precio_unitario is not None
                else catalogo[ln.producto_id].precio_venta
            ),
            agotado=ln.agotado,
            justificacion=(ln.justificacion_carga or "").strip() or None,
        )
        for ln in solicitud.lineas
    ]
    etiquetas = {pid: c.sku for pid, c in catalogo.items()}
    validar_hay_movimiento(lineas)
    validar_unidades_no_exceden(lineas, etiquetas)

    advertencias = _validar_contra_carga(db, solicitud, lineas, etiquetas)
    return _Preparada(ruta, vendedor_id, lineas, catalogo, advertencias)


def _cargado_despachado(
    db: Session, ruta_id: uuid.UUID, fecha: date
) -> tuple[uuid.UUID | None, dict[uuid.UUID, Decimal]]:
    """`(carga_id, producto -> cantidad)` de lo despachado a la ruta ese día (sin carga: `None`)."""
    cargas = carga_repo.despachadas_de_ruta(db, ruta_id, fecha)
    if not cargas:
        return None, {}
    cantidades: dict[uuid.UUID, Decimal] = {}
    for carga in cargas:
        for d in carga.detalles:
            cantidades[d.producto_id] = cantidades.get(d.producto_id, _CERO) + (
                d.cantidad_aprobada or _CERO
            )
    return cargas[0].id, cantidades


def _validar_contra_carga(
    db: Session,
    solicitud: LiquidacionRequest,
    lineas: Sequence[LineaCalculada],
    etiquetas: Mapping[uuid.UUID, str],
) -> list[str]:
    """Con carga despachada, editar `cantidad_cargada` exige justificación; sin carga solo avisa."""
    carga_id, despachado = _cargado_despachado(db, solicitud.ruta_id, solicitud.fecha)
    if carga_id is None:
        return [
            "No hay una carga despachada para la ruta y fecha: se tomó lo cargado tal como se "
            "ingresó."
        ]
    sin_justificar = {
        etiquetas.get(ln.producto_id, str(ln.producto_id)): {
            "despachada": str(despachado.get(ln.producto_id, _CERO)),
            "ingresada": str(ln.cargada),
        }
        for ln in lineas
        if ln.cargada != despachado.get(ln.producto_id, _CERO) and not ln.justificacion
    }
    if sin_justificar:
        raise AppError(
            "CARGA_REQUIERE_JUSTIFICACION",
            "La cantidad cargada difiere de la carga despachada: indique la justificación.",
            detalle={"productos": sin_justificar},
        )
    ausentes = sorted(str(p) for p, q in despachado.items() if q > 0 and p not in etiquetas)
    return (
        [
            f"La carga despachada incluía {len(ausentes)} presentaciones que no están en la "
            "liquidación."
        ]
        if ausentes
        else []
    )


# ====================================================================== guardar borrador
@auditar
def guardar_borrador(
    db: Session, solicitud: LiquidacionRequest, usuario_id: uuid.UUID
) -> LiquidacionResponse:
    """Crea o actualiza el borrador de la fecha/ruta/vendedor. No toca `ventas_historicas`."""
    prep = _preparar(db, solicitud)
    existente = liquidacion_repo.vigente(db, solicitud.fecha, solicitud.ruta_id, prep.vendedor_id)
    if existente is not None and existente.estado == EstadoLiquidacion.CERRADA:
        raise AppError(
            "LIQUIDACION_DUPLICADA",
            "Ya existe una liquidación cerrada para la fecha, ruta y vendedor: use «corregir».",
            status_code=409,
            detalle={"liquidacion_id": str(existente.id), "estado": existente.estado},
        )

    valores = _valores_cabecera(prep.lineas, solicitud.pagos, solicitud.observaciones)
    detalles = _filas_detalle(prep.lineas)
    if existente is None:
        try:
            liquidacion = liquidacion_repo.crear(
                db,
                cabecera={
                    "fecha": solicitud.fecha,
                    "ruta_id": solicitud.ruta_id,
                    "vendedor_id": prep.vendedor_id,
                    "estado": EstadoLiquidacion.BORRADOR,
                    "creado_por": usuario_id,
                    **valores,
                },
                detalles=detalles,
            )
        except IntegrityError as exc:  # carrera con otro borrador: lo decide el índice único
            db.rollback()
            raise _duplicada() from exc
        _registrar_evento(liquidacion, "creada", usuario_id, antes=None)
    else:
        antes = _instantanea(existente)
        for campo, valor in valores.items():
            setattr(existente, campo, valor)
        liquidacion_repo.reemplazar_lineas(db, existente, detalles)
        liquidacion = existente
        _registrar_evento(liquidacion, "actualizada", usuario_id, antes=antes)

    advertencias = [*prep.advertencias, *_advertencias_cuadre(prep.lineas, solicitud.pagos)]
    db.commit()
    return _respuesta(db, liquidacion, advertencias=advertencias)


def _duplicada() -> AppError:
    return AppError(
        "LIQUIDACION_DUPLICADA",
        "Ya existe una liquidación para la fecha, ruta y vendedor.",
        status_code=409,
    )


def _advertencias_cuadre(lineas: Sequence[LineaCalculada], pagos: PagosLiquidacion) -> list[str]:
    avisos = []
    pendientes = [ln for ln in lineas if ln.diferencia != 0]
    if pendientes:
        avisos.append(
            f"{len(pendientes)} presentaciones no cuadran (cargada ≠ vendida + devuelta + merma); "
            "debe corregirse antes de cerrar."
        )
    venta = total_venta(lineas)
    if venta != total_pagos(pagos):
        avisos.append(
            "La venta total no coincide con efectivo + transferencia + crédito; debe cuadrar "
            "antes de cerrar."
        )
    return avisos


def _valores_cabecera(
    lineas: Sequence[LineaCalculada], pagos: PagosLiquidacion, observaciones: str | None
) -> dict[str, Any]:
    esperado, diferencia = calcular_caja(pagos)
    return {
        "venta_total": total_venta(lineas),
        "total_efectivo": pagos.efectivo,
        "total_transferencia": pagos.transferencia,
        "total_credito": pagos.credito,
        "cobro_saldos_anteriores": pagos.cobro_saldos,
        "gastos_ruta": pagos.gastos,
        "efectivo_esperado": esperado,
        "efectivo_entregado": pagos.efectivo_entregado,
        "diferencia_caja": diferencia,
        "observaciones": (observaciones or "").strip() or None,
    }


def _filas_detalle(lineas: Sequence[LineaCalculada]) -> list[dict[str, Any]]:
    return [
        {
            "producto_id": ln.producto_id,
            "cantidad_cargada": ln.cargada,
            "cantidad_vendida": ln.vendida,
            "cantidad_devuelta": ln.devuelta,
            "cantidad_merma": ln.merma,
            "precio_unitario": ln.precio,
            "monto_total": ln.monto,
            "agotado": ln.agotado,
            "justificacion_carga": ln.justificacion,
        }
        for ln in lineas
    ]


def _lineas_de(liquidacion: LiquidacionDiaria) -> list[LineaCalculada]:
    return [
        LineaCalculada(
            producto_id=d.producto_id,
            cargada=d.cantidad_cargada,
            vendida=d.cantidad_vendida,
            devuelta=d.cantidad_devuelta,
            merma=d.cantidad_merma,
            precio=d.precio_unitario,
            agotado=d.agotado,
            justificacion=d.justificacion_carga,
        )
        for d in liquidacion.detalles
    ]


def _pagos_de(liquidacion: LiquidacionDiaria) -> PagosLiquidacion:
    return PagosLiquidacion(
        efectivo=liquidacion.total_efectivo,
        transferencia=liquidacion.total_transferencia,
        credito=liquidacion.total_credito,
        cobro_saldos=liquidacion.cobro_saldos_anteriores,
        gastos=liquidacion.gastos_ruta,
        efectivo_entregado=liquidacion.efectivo_entregado,
    )


# ====================================================================== cerrar / corregir / anular
@auditar
def cerrar(db: Session, liquidacion_id: uuid.UUID, usuario_id: uuid.UUID) -> LiquidacionResponse:
    """`borrador → cerrada`: valida cuadres y alimenta ventas, demanda real, monitoreo y caja."""
    liquidacion = _obtener_bloqueada(db, liquidacion_id)
    if liquidacion.estado == EstadoLiquidacion.CERRADA:
        raise AppError(
            "LIQUIDACION_YA_CERRADA",
            "La liquidación ya está cerrada: use «corregir».",
            status_code=409,
        )
    _exigir_no_anulada(liquidacion)

    lineas = _lineas_de(liquidacion)
    etiquetas = _etiquetas(db, lineas)
    _revalidar_catalogo(db, lineas)
    exigir_unidades_cuadran(lineas, etiquetas)
    exigir_montos_cuadran(total_venta(lineas), _pagos_de(liquidacion))

    antes = _instantanea(liquidacion)
    advertencias, alerta_id = _aplicar_cierre(
        db, liquidacion, lineas, usuario_id, productos_previos=()
    )
    _registrar_evento(liquidacion, "cerrada", usuario_id, antes=antes)
    db.commit()
    return _respuesta(db, liquidacion, advertencias=advertencias, alerta_id=alerta_id)


@auditar
def corregir(
    db: Session, liquidacion_id: uuid.UUID, solicitud: CorreccionRequest, usuario_id: uuid.UUID
) -> LiquidacionResponse:
    """Corrige una liquidación cerrada: nueva versión, UPSERT de ventas, `demanda_real` recalculada
    y evaluación encolada de nuevo."""
    liquidacion = _obtener_bloqueada(db, liquidacion_id)
    _exigir_no_anulada(liquidacion)
    if liquidacion.estado != EstadoLiquidacion.CERRADA:
        raise AppError(
            "LIQUIDACION_NO_CERRADA",
            "Solo se corrige una liquidación cerrada; un borrador se edita con «guardar».",
            status_code=409,
        )
    if (
        solicitud.fecha != liquidacion.fecha
        or solicitud.ruta_id != liquidacion.ruta_id
        or (solicitud.vendedor_id or liquidacion.vendedor_id) != liquidacion.vendedor_id
    ):
        raise AppError(
            "CORRECCION_CAMBIA_CLAVE",
            "Una corrección no puede cambiar la fecha, la ruta ni el vendedor: anule y cree otra.",
        )

    prep = _preparar(db, solicitud)
    etiquetas = {pid: c.sku for pid, c in prep.catalogo.items()}
    exigir_unidades_cuadran(prep.lineas, etiquetas)
    exigir_montos_cuadran(total_venta(prep.lineas), solicitud.pagos)

    antes = _instantanea(liquidacion)
    productos_previos = {d.producto_id for d in liquidacion.detalles}
    for campo, valor in _valores_cabecera(
        prep.lineas, solicitud.pagos, solicitud.observaciones
    ).items():
        setattr(liquidacion, campo, valor)
    liquidacion_repo.reemplazar_lineas(db, liquidacion, _filas_detalle(prep.lineas))
    liquidacion.version += 1

    advertencias, alerta_id = _aplicar_cierre(
        db, liquidacion, prep.lineas, usuario_id, productos_previos=productos_previos
    )
    _registrar_evento(liquidacion, "corregida", usuario_id, antes=antes, motivo=solicitud.motivo)
    db.commit()
    return _respuesta(
        db, liquidacion, advertencias=[*prep.advertencias, *advertencias], alerta_id=alerta_id
    )


@auditar
def anular(
    db: Session, liquidacion_id: uuid.UUID, motivo: str, usuario_id: uuid.UUID
) -> LiquidacionResponse:
    """Anula una liquidación: si estaba cerrada revierte su efecto en `ventas_historicas`."""
    liquidacion = _obtener_bloqueada(db, liquidacion_id)
    _exigir_no_anulada(liquidacion)

    antes = _instantanea(liquidacion)
    if liquidacion.estado == EstadoLiquidacion.CERRADA:
        lote = sales_repo.obtener_lote(db, liquidacion.lote_id) if liquidacion.lote_id else None
        if lote is not None:
            sales_repo.eliminar_ventas_de_lote(db, lote.id)
            sales_repo.sellar_lote_anulado(
                db,
                lote,
                checksum_anulado(lote.checksum_sha256, liquidacion.id, liquidacion.version),
            )
        forecast_repo.limpiar_demanda_real_dia(
            db,
            liquidacion.fecha,
            liquidacion.ruta_id,
            [d.producto_id for d in liquidacion.detalles],
        )
    alert_repo.resolver_abiertas_con_marca(
        db, tipo=TipoAlerta.DIFERENCIA_CAJA, marca=str(liquidacion.id)
    )
    liquidacion.estado = EstadoLiquidacion.ANULADA
    liquidacion.anulado_en = datetime.now(UTC)
    liquidacion.anulado_motivo = motivo
    _registrar_evento(liquidacion, "anulada", usuario_id, antes=antes, motivo=motivo)
    db.commit()
    return _respuesta(db, liquidacion)


def _obtener_bloqueada(db: Session, liquidacion_id: uuid.UUID) -> LiquidacionDiaria:
    liquidacion = liquidacion_repo.obtener(db, liquidacion_id, bloquear=True)
    if liquidacion is None:
        raise AppError(
            "LIQUIDACION_NO_ENCONTRADA", "La liquidación indicada no existe.", status_code=404
        )
    return liquidacion


def _exigir_no_anulada(liquidacion: LiquidacionDiaria) -> None:
    if liquidacion.estado == EstadoLiquidacion.ANULADA:
        raise AppError("LIQUIDACION_YA_ANULADA", "La liquidación ya está anulada.", status_code=409)


def _revalidar_catalogo(db: Session, lineas: Sequence[LineaCalculada]) -> None:
    catalogo = catalog_repo.productos_para_liquidacion(db, [ln.producto_id for ln in lineas])
    inactivos = sorted(c.sku for c in catalogo.values() if not c.activo)
    if inactivos:
        raise AppError(
            "PRODUCTO_INACTIVO", "Uno o más productos están inactivos.", detalle={"skus": inactivos}
        )


def _etiquetas(db: Session, lineas: Sequence[LineaCalculada]) -> dict[uuid.UUID, str]:
    return catalog_repo.skus_de(db, [ln.producto_id for ln in lineas])


def _aplicar_cierre(
    db: Session,
    liquidacion: LiquidacionDiaria,
    lineas: Sequence[LineaCalculada],
    usuario_id: uuid.UUID,
    *,
    productos_previos: Sequence[uuid.UUID] | set[uuid.UUID],
) -> tuple[list[str], uuid.UUID | None]:
    """Efecto del cierre (o de una corrección) sobre ventas, demanda real, caja y monitoreo.

    Corre dentro de la transacción del caso de uso: o se aplica todo o nada.
    """
    if sales_repo.hay_ventas_excel(db, liquidacion.fecha, liquidacion.ruta_id):
        raise AppError(
            "VENTAS_EXCEL_EXISTENTES",
            "La línea base de Excel ya trae ventas de esa ruta y fecha; no se sobrescribe.",
            status_code=409,
            detalle={"fecha": liquidacion.fecha.isoformat(), "ruta_id": str(liquidacion.ruta_id)},
        )
    advertencias: list[str] = []

    # --- lote (uno por liquidación) y ventas históricas
    checksum = calcular_checksum(
        liquidacion.fecha, liquidacion.ruta_id, liquidacion.vendedor_id, lineas
    )
    con_venta = [ln for ln in lineas if ln.vendida > 0]
    if liquidacion.lote_id is None:
        ruta = catalog_repo.obtener_ruta(db, liquidacion.ruta_id)
        nombre = (
            f"liquidacion {liquidacion.fecha.isoformat()} {ruta.codigo if ruta else ''}".strip()
        )
        lote = sales_repo.crear_lote_liquidacion(
            db,
            usuario_id=usuario_id,
            archivo_nombre=nombre,
            checksum=checksum,
            filas=len(con_venta),
        )
        liquidacion.lote_id = lote.id
    else:
        lote = sales_repo.obtener_lote(db, liquidacion.lote_id)
        assert lote is not None
        sales_repo.actualizar_lote_liquidacion(
            db, lote, usuario_id=usuario_id, checksum=checksum, filas=len(con_venta)
        )
    sales_repo.eliminar_ventas_de_lote(
        db, lote.id, conservar_productos={ln.producto_id for ln in con_venta}
    )
    persistidas = sales_repo.upsert_ventas(
        db,
        [
            {
                "lote_id": lote.id,
                "fecha_venta": liquidacion.fecha,
                "producto_id": ln.producto_id,
                "ruta_id": liquidacion.ruta_id,
                "vendedor_id": liquidacion.vendedor_id,
                "cantidad": ln.vendida,
                "precio_unitario": ln.precio,
                "monto_total": ln.monto,
            }
            for ln in con_venta
        ],
    )
    advertencias.extend(etl_service.generar_comisiones(db, persistidas))

    # --- demanda real de los pronósticos (el producto quitado en una corrección queda en 0)
    reales: dict[uuid.UUID, tuple[Decimal, bool]] = {
        pid: (_CERO, False) for pid in productos_previos
    }
    reales.update({ln.producto_id: (ln.vendida, ln.agotado) for ln in lineas})
    forecast_repo.fijar_demanda_real_dia(db, liquidacion.fecha, liquidacion.ruta_id, reales)

    # --- cuadre de caja: la diferencia no bloquea; sobre el umbral genera alerta
    alerta_id = _alertar_diferencia_caja(db, liquidacion, advertencias)

    # --- monitoreo: evaluate_production corre en el Worker, nunca dentro de la petición
    _encolar_evaluacion(db, usuario_id, liquidacion)

    liquidacion.estado = EstadoLiquidacion.CERRADA
    liquidacion.cerrado_en = datetime.now(UTC)
    db.flush()
    return advertencias, alerta_id


def _alertar_diferencia_caja(
    db: Session, liquidacion: LiquidacionDiaria, advertencias: list[str]
) -> uuid.UUID | None:
    alert_repo.resolver_abiertas_con_marca(
        db, tipo=TipoAlerta.DIFERENCIA_CAJA, marca=str(liquidacion.id)
    )
    umbral = obtener_config(db).umbral_diferencia_caja
    if not supera_umbral(liquidacion.diferencia_caja, umbral):
        return None
    ruta = catalog_repo.obtener_ruta(db, liquidacion.ruta_id)
    sentido = "faltante" if liquidacion.diferencia_caja < 0 else "sobrante"
    mensaje = (
        f"Diferencia de caja: {sentido} de Q {abs(liquidacion.diferencia_caja):,.2f} en la "
        f"liquidación del {liquidacion.fecha.isoformat()} de la ruta "
        f"{ruta.nombre if ruta else liquidacion.ruta_id} (umbral Q {umbral:,.2f}). "
        f"Liquidación {liquidacion.id}."
    )
    alerta = alert_repo.crear(
        db, tipo=TipoAlerta.DIFERENCIA_CAJA, severidad=Severidad.ADVERTENCIA, mensaje=mensaje
    )
    advertencias.append(f"La diferencia de caja supera el umbral de Q {umbral:,.2f}.")
    return alerta.id


def _encolar_evaluacion(db: Session, usuario_id: uuid.UUID, liquidacion: LiquidacionDiaria) -> None:
    """Un solo job `evaluacion_produccion` en cola: varias liquidaciones seguidas se coalescen."""
    if job_repo.en_cola_de_tipo(db, TipoJob.EVALUACION_PRODUCCION) is not None:
        return
    job_repo.crear(
        db,
        tipo=TipoJob.EVALUACION_PRODUCCION,
        solicitado_por=usuario_id,
        parametros={
            "origen": "liquidacion",
            "fecha": liquidacion.fecha.isoformat(),
            "liquidacion_id": str(liquidacion.id),
        },
    )


# ====================================================================== auditoría
def _instantanea(liquidacion: LiquidacionDiaria) -> dict[str, Any]:
    return {
        "estado": liquidacion.estado,
        "version": liquidacion.version,
        "venta_total": str(liquidacion.venta_total),
        "efectivo_entregado": str(liquidacion.efectivo_entregado),
        "diferencia_caja": str(liquidacion.diferencia_caja),
        "lineas": [
            {
                "producto_id": str(d.producto_id),
                "cargada": str(d.cantidad_cargada),
                "vendida": str(d.cantidad_vendida),
                "devuelta": str(d.cantidad_devuelta),
                "merma": str(d.cantidad_merma),
                "precio": str(d.precio_unitario),
                "agotado": d.agotado,
            }
            for d in sorted(liquidacion.detalles, key=lambda x: str(x.producto_id))
        ],
    }


def _registrar_evento(
    liquidacion: LiquidacionDiaria,
    accion: str,
    usuario_id: uuid.UUID,
    *,
    antes: dict[str, Any] | None,
    motivo: str | None = None,
) -> None:
    """Deja traza en la bitácora de la liquidación y en el logger `app.auditoria`."""
    evento = {
        "accion": accion,
        "usuario_id": str(usuario_id),
        "en": datetime.now(UTC).isoformat(),
        "motivo": motivo,
        "antes": antes,
        "despues": _instantanea(liquidacion),
    }
    liquidacion.historial = [*(liquidacion.historial or []), evento]
    auditoria.info(
        "LIQUIDACION_%s usuario=%s liquidacion=%s version=%s",
        accion.upper(),
        usuario_id,
        liquidacion.id,
        liquidacion.version,
        extra={"evento": evento},
    )


# ====================================================================== consultas
@auditar
def obtener(db: Session, liquidacion_id: uuid.UUID) -> LiquidacionResponse:
    liquidacion = liquidacion_repo.obtener(db, liquidacion_id)
    if liquidacion is None:
        raise AppError(
            "LIQUIDACION_NO_ENCONTRADA", "La liquidación indicada no existe.", status_code=404
        )
    return _respuesta(db, liquidacion)


@auditar
def listar(
    db: Session,
    *,
    desde: date | None,
    hasta: date | None,
    ruta_id: uuid.UUID | None,
    vendedor_id: uuid.UUID | None,
    estado: EstadoLiquidacion | None,
    limit: int,
    offset: int,
) -> ListadoLiquidaciones:
    if desde is not None and hasta is not None and desde > hasta:
        raise AppError(
            "RANGO_FECHAS_INVALIDO",
            "El campo `desde` no puede ser posterior a `hasta`.",
            status_code=422,
            detalle={"campo": "desde"},
        )
    filas, total = liquidacion_repo.listar(
        db,
        desde=desde,
        hasta=hasta,
        ruta_id=ruta_id,
        vendedor_id=vendedor_id,
        estado=estado,
        limit=limit,
        offset=offset,
    )
    return ListadoLiquidaciones(
        total=total,
        liquidaciones=[
            LiquidacionResumen(
                id=liq.id,
                fecha=liq.fecha,
                ruta_id=liq.ruta_id,
                ruta_nombre=ruta,
                vendedor_id=liq.vendedor_id,
                vendedor_nombre=vendedor,
                estado=EstadoLiquidacion(liq.estado),
                version=liq.version,
                unidades_vendidas=unidades,
                venta_total=liq.venta_total,
                diferencia_caja=liq.diferencia_caja,
                cerrado_en=liq.cerrado_en,
            )
            for liq, ruta, vendedor, unidades in filas
        ],
    )


@auditar
def precargar(
    db: Session, fecha: date, ruta_id: uuid.UUID, vendedor_id: uuid.UUID | None = None
) -> PrecargaResponse:
    """Datos para abrir la pantalla: lo despachado a la ruta (editable) y la liquidación vigente."""
    validar_fecha(fecha)
    ruta = catalog_repo.obtener_ruta(db, ruta_id)
    if ruta is None:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta indicada no existe.")
    vendedor_id = vendedor_id or ruta.vendedor_id

    carga_id, despachado = _cargado_despachado(db, ruta_id, fecha)
    advertencias: list[str] = []
    if carga_id is None:
        advertencias.append(
            "No hay una carga despachada para la ruta y fecha: ingrese lo cargado manualmente."
        )
        productos = sales_repo.productos_de_ruta(db, ruta_id)
        despachado = {pid: _CERO for pid in productos}
    catalogo = catalog_repo.productos_para_liquidacion(db, despachado)
    lineas = [
        LineaPrecarga(
            producto_id=pid,
            sku=catalogo[pid].sku,
            producto_nombre=catalogo[pid].nombre,
            cantidad_cargada=cantidad,
            precio_unitario=catalogo[pid].precio_venta,
        )
        for pid, cantidad in sorted(despachado.items(), key=lambda kv: catalogo[kv[0]].sku)
        if pid in catalogo and catalogo[pid].activo
    ]
    existente = liquidacion_repo.vigente(db, fecha, ruta_id, vendedor_id)
    return PrecargaResponse(
        fecha=fecha,
        ruta_id=ruta_id,
        vendedor_id=vendedor_id,
        carga_id=carga_id,
        lineas=lineas,
        liquidacion=None if existente is None else _respuesta(db, existente),
        advertencias=advertencias,
    )


# ====================================================================== respuesta
def construir_respuesta(
    liquidacion: LiquidacionDiaria,
    *,
    catalogo: Mapping[uuid.UUID, tuple[str, str]],
    ruta_nombre: str,
    vendedor_nombre: str,
    umbral: Decimal,
    advertencias: Sequence[str] = (),
    alerta_id: uuid.UUID | None = None,
) -> LiquidacionResponse:
    """DTO de respuesta con los cuadres de unidades y dinero ya calculados (sin acceso a BD)."""
    lineas = [
        LineaRespuesta(
            producto_id=d.producto_id,
            sku=catalogo[d.producto_id][0],
            producto_nombre=catalogo[d.producto_id][1],
            cantidad_cargada=d.cantidad_cargada,
            cantidad_vendida=d.cantidad_vendida,
            cantidad_devuelta=d.cantidad_devuelta,
            cantidad_merma=d.cantidad_merma,
            precio_unitario=d.precio_unitario,
            monto_total=d.monto_total,
            agotado=d.agotado,
            justificacion_carga=d.justificacion_carga,
            diferencia_unidades=d.cantidad_cargada
            - d.cantidad_vendida
            - d.cantidad_devuelta
            - d.cantidad_merma,
            cuadra=d.cantidad_cargada - d.cantidad_vendida - d.cantidad_devuelta - d.cantidad_merma
            == 0,
        )
        for d in sorted(liquidacion.detalles, key=lambda x: catalogo[x.producto_id][0])
    ]
    pagos = _pagos_de(liquidacion)
    suma_pagos = total_pagos(pagos)
    return LiquidacionResponse(
        id=liquidacion.id,
        fecha=liquidacion.fecha,
        ruta_id=liquidacion.ruta_id,
        ruta_nombre=ruta_nombre,
        vendedor_id=liquidacion.vendedor_id,
        vendedor_nombre=vendedor_nombre,
        estado=EstadoLiquidacion(liquidacion.estado),
        version=liquidacion.version,
        lote_id=liquidacion.lote_id,
        lineas=lineas,
        pagos=pagos,
        cuadre_unidades=CuadreUnidades(
            cargadas=sum((ln.cantidad_cargada for ln in lineas), _CERO),
            vendidas=sum((ln.cantidad_vendida for ln in lineas), _CERO),
            devueltas=sum((ln.cantidad_devuelta for ln in lineas), _CERO),
            merma=sum((ln.cantidad_merma for ln in lineas), _CERO),
            diferencia=sum((ln.diferencia_unidades for ln in lineas), _CERO),
            cuadra=all(ln.cuadra for ln in lineas),
        ),
        cuadre_dinero=CuadreDinero(
            venta_total=liquidacion.venta_total,
            total_pagos=suma_pagos,
            diferencia_venta_pagos=liquidacion.venta_total - suma_pagos,
            cuadra=liquidacion.venta_total == suma_pagos,
            efectivo_esperado=liquidacion.efectivo_esperado,
            efectivo_entregado=liquidacion.efectivo_entregado,
            diferencia_caja=liquidacion.diferencia_caja,
            umbral_diferencia_caja=umbral,
            supera_umbral=supera_umbral(liquidacion.diferencia_caja, umbral),
        ),
        devolucion_esperada=sum((ln.cantidad_devuelta for ln in lineas), _CERO),
        observaciones=liquidacion.observaciones,
        advertencias=list(advertencias),
        alerta_id=alerta_id,
        creado_en=liquidacion.creado_en,
        cerrado_en=liquidacion.cerrado_en,
        anulado_en=liquidacion.anulado_en,
        anulado_motivo=liquidacion.anulado_motivo,
    )


def _respuesta(
    db: Session,
    liquidacion: LiquidacionDiaria,
    *,
    advertencias: Sequence[str] = (),
    alerta_id: uuid.UUID | None = None,
) -> LiquidacionResponse:
    catalogo = catalog_repo.productos_resumen(db, [d.producto_id for d in liquidacion.detalles])
    ruta = catalog_repo.obtener_ruta(db, liquidacion.ruta_id)
    vendedor = user_repo.obtener_por_id(db, liquidacion.vendedor_id)
    return construir_respuesta(
        liquidacion,
        catalogo=catalogo,
        ruta_nombre=ruta.nombre if ruta else "",
        vendedor_nombre=vendedor.nombre_completo if vendedor else "",
        umbral=obtener_config(db).umbral_diferencia_caja,
        advertencias=advertencias,
        alerta_id=alerta_id,
    )


# ====================================================================== configuración
@auditar
def obtener_config(db: Session) -> LiquidacionConfig:
    valor = parametro_repo.obtener_valor(db, parametros.UMBRAL_DIFERENCIA_CAJA)
    try:
        umbral = Decimal(str(valor)).quantize(_CENTAVOS, ROUND_HALF_UP)
        if umbral < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        umbral = parametros.UMBRAL_DIFERENCIA_CAJA_POR_DEFECTO
    return LiquidacionConfig(umbral_diferencia_caja=umbral)


@auditar
def actualizar_config(
    db: Session, config: LiquidacionConfig, usuario_id: uuid.UUID
) -> LiquidacionConfig:
    anterior = obtener_config(db)
    parametro_repo.guardar_valor(
        db,
        parametros.UMBRAL_DIFERENCIA_CAJA,
        float(config.umbral_diferencia_caja),
        actualizado_por=usuario_id,
    )
    auditoria.info(
        "CONFIG_LIQUIDACION usuario=%s antes=%s despues=%s",
        usuario_id,
        anterior.umbral_diferencia_caja,
        config.umbral_diferencia_caja,
    )
    db.commit()
    return config
