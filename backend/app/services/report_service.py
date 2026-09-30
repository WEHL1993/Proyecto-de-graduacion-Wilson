"""Reportes gerenciales (Módulo 7): rotación e índice de quiebres, liquidación de comisiones y
venta real vs. proyectada, más su exportación a CSV/Excel."""

import re
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import report_repo
from app.schemas.reports import (
    ComisionReporte,
    ComisionVendedor,
    FormatoReporte,
    RotacionReporte,
    RotacionRuta,
    TipoReporte,
    VentaProyeccionDia,
    VentaProyeccionRuta,
    VentasProyeccionReporte,
)
from app.services import report_export
from app.services.report_export import Tabla

CERO = Decimal("0")
_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DIAS_POR_DEFECTO = 30


def _q(valor: Decimal, decimales: int = 2) -> Decimal:
    return valor.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def _razon(numerador: Decimal, denominador: Decimal, decimales: int = 2) -> Decimal | None:
    return None if denominador == 0 else _q(numerador / denominador, decimales)


def _pct(parte: Decimal, total: Decimal) -> Decimal | None:
    return None if total == 0 else _q(parte * 100 / total)


def _rango(
    db: Session, desde: date | None, hasta: date | None, *, con_proyeccion: bool = False
) -> tuple[date, date]:
    if hasta is None:
        hasta = report_repo.rango_por_defecto(db, con_proyeccion=con_proyeccion) or date.today()
    if desde is None:
        desde = hasta - timedelta(days=_DIAS_POR_DEFECTO - 1)
    if desde > hasta:
        raise AppError("RANGO_INVALIDO", "`desde` no puede ser posterior a `hasta`.")
    return desde, hasta


def _validar_periodo(periodo: str | None) -> str | None:
    if periodo is not None and not _PERIODO.match(periodo):
        raise AppError("PERIODO_INVALIDO", f"Periodo '{periodo}' inválido; use YYYY-MM.")
    return periodo


# ---------------------------------------------------------------- rotación y quiebres
def rotacion_e_indice_quiebres(
    db: Session, desde: date | None, hasta: date | None, ruta_id: uuid.UUID | None
) -> RotacionReporte:
    desde, hasta = _rango(db, desde, hasta)
    rutas = report_repo.rutas(db, ruta_id)
    if ruta_id is not None and ruta_id not in rutas:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta no existe.", status_code=404)

    ventas = {v.ruta_id: v for v in report_repo.ventas_por_ruta(db, desde, hasta, ruta_id)}
    quiebres = {q.ruta_id: q for q in report_repo.quiebres_por_ruta(db, desde, hasta, ruta_id)}
    inventario = report_repo.valor_inventario(db)
    costo_total = sum((v.costo for v in ventas.values()), CERO)
    lineas = sum(q.lineas for q in quiebres.values())
    ajustadas = sum(q.ajustadas for q in quiebres.values())

    filas: list[RotacionRuta] = []
    for id_, ruta in rutas.items():
        venta, quiebre = ventas.get(id_), quiebres.get(id_)
        if venta is None and quiebre is None:
            continue
        costo = venta.costo if venta else CERO
        filas.append(
            RotacionRuta(
                ruta_id=id_,
                ruta_codigo=ruta.codigo,
                ruta_nombre=ruta.nombre,
                unidades_vendidas=venta.unidades if venta else CERO,
                monto_vendido=venta.monto if venta else CERO,
                costo_ventas=_q(costo),
                rotacion=_razon(costo, inventario, 4),
                cargas=quiebre.cargas if quiebre else 0,
                lineas_carga=quiebre.lineas if quiebre else 0,
                lineas_ajustadas=quiebre.ajustadas if quiebre else 0,
                indice_quiebre=_pct(Decimal(quiebre.ajustadas), Decimal(quiebre.lineas))
                if quiebre
                else None,
                unidades_no_cubiertas=quiebre.no_cubiertas if quiebre else CERO,
            )
        )
    rotacion = _razon(costo_total, inventario, 4)
    dias = (hasta - desde).days + 1
    return RotacionReporte(
        desde=desde,
        hasta=hasta,
        valor_inventario=_q(inventario),
        costo_ventas_total=_q(costo_total),
        rotacion_global=rotacion,
        dias_inventario=_razon(Decimal(dias), rotacion, 1) if rotacion else None,
        indice_quiebre_global=_pct(Decimal(ajustadas), Decimal(lineas)),
        rutas=sorted(filas, key=lambda f: f.costo_ventas, reverse=True),
    )


# ---------------------------------------------------------------- comisiones
def liquidacion_comisiones(
    db: Session,
    periodo_desde: str | None,
    periodo_hasta: str | None,
    vendedor_id: uuid.UUID | None,
    ruta_id: uuid.UUID | None,
) -> ComisionReporte:
    desde, hasta = _validar_periodo(periodo_desde), _validar_periodo(periodo_hasta)
    if hasta is None:
        hasta = desde or (report_repo.rango_por_defecto(db) or date.today()).strftime("%Y-%m")
    desde = desde or hasta
    if desde > hasta:
        raise AppError(
            "RANGO_INVALIDO", "`periodo_desde` no puede ser posterior a `periodo_hasta`."
        )

    filas = report_repo.liquidacion_comisiones(db, desde, hasta, vendedor_id, ruta_id)
    liquidaciones = [
        ComisionVendedor(
            vendedor_id=f.vendedor_id,
            vendedor=f.vendedor,
            periodo=f.periodo,
            ventas_registradas=f.ventas,
            monto_vendido=f.monto_vendido,
            comision_total=f.comision,
            porcentaje_efectivo=_pct(f.comision, f.monto_vendido),
        )
        for f in filas
    ]
    return ComisionReporte(
        periodo_desde=desde,
        periodo_hasta=hasta,
        total_vendido=sum((f.monto_vendido for f in filas), CERO),
        total_comisiones=sum((f.comision for f in filas), CERO),
        liquidaciones=liquidaciones,
    )


# ---------------------------------------------------------------- real vs proyectado
def ventas_vs_proyeccion(
    db: Session, desde: date | None, hasta: date | None, ruta_id: uuid.UUID | None
) -> VentasProyeccionReporte:
    desde, hasta = _rango(db, desde, hasta, con_proyeccion=True)
    rutas = report_repo.rutas(db, ruta_id)
    if ruta_id is not None and ruta_id not in rutas:
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta no existe.", status_code=404)

    real = report_repo.real_por_ruta(db, desde, hasta, ruta_id)
    proyectada = report_repo.proyectado_por_ruta(db, desde, hasta, ruta_id)
    por_ruta = [
        VentaProyeccionRuta(
            ruta_id=id_,
            ruta_codigo=ruta.codigo,
            ruta_nombre=ruta.nombre,
            real=real.get(id_, CERO),
            proyectada=_q(proyectada.get(id_, CERO)),
            desviacion_pct=_pct(real.get(id_, CERO) - proyectada.get(id_, CERO), proyectada[id_])
            if proyectada.get(id_)
            else None,
        )
        for id_, ruta in rutas.items()
        if id_ in real or id_ in proyectada
    ]

    real_dia = report_repo.real_por_dia(db, desde, hasta, ruta_id)
    proy_dia = report_repo.proyectado_por_dia(db, desde, hasta, ruta_id)
    serie = [
        VentaProyeccionDia(
            fecha=f, real=real_dia.get(f, CERO), proyectada=_q(proy_dia.get(f, CERO))
        )
        for f in sorted(real_dia.keys() | proy_dia.keys())
    ]
    return VentasProyeccionReporte(
        desde=desde,
        hasta=hasta,
        total_real=sum(real.values(), CERO),
        total_proyectado=_q(sum(proyectada.values(), CERO)),
        rutas=por_ruta,
        serie=serie,
    )


# ---------------------------------------------------------------- exportación
def _tabla_rotacion(r: RotacionReporte) -> Tabla:
    return Tabla(
        "Rotación y quiebres",
        [
            "Ruta",
            "Nombre",
            "Unidades vendidas",
            "Monto vendido",
            "Costo de ventas",
            "Rotación",
            "Cargas",
            "Líneas de carga",
            "Líneas ajustadas por stock",
            "Índice de quiebre (%)",
            "Unidades no cubiertas",
        ],
        [
            [
                f.ruta_codigo,
                f.ruta_nombre,
                f.unidades_vendidas,
                f.monto_vendido,
                f.costo_ventas,
                f.rotacion,
                f.cargas,
                f.lineas_carga,
                f.lineas_ajustadas,
                f.indice_quiebre,
                f.unidades_no_cubiertas,
            ]
            for f in r.rutas
        ],
    )


def _tabla_comisiones(c: ComisionReporte) -> Tabla:
    return Tabla(
        "Comisiones",
        ["Periodo", "Vendedor", "Ventas", "Monto vendido", "Comisión", "% efectivo"],
        [
            [
                f.periodo,
                f.vendedor,
                f.ventas_registradas,
                f.monto_vendido,
                f.comision_total,
                f.porcentaje_efectivo,
            ]
            for f in c.liquidaciones
        ],
    )


def _tabla_ventas(v: VentasProyeccionReporte) -> Tabla:
    return Tabla(
        "Real vs proyectado",
        ["Ruta", "Nombre", "Venta real (uds)", "Proyectada (uds)", "Desviación (%)"],
        [[f.ruta_codigo, f.ruta_nombre, f.real, f.proyectada, f.desviacion_pct] for f in v.rutas],
    )


def exportar(
    db: Session,
    tipo: TipoReporte,
    formato: FormatoReporte,
    *,
    desde: date | None,
    hasta: date | None,
    periodo_desde: str | None,
    periodo_hasta: str | None,
    ruta_id: uuid.UUID | None,
) -> tuple[bytes, str, str]:
    """`(contenido, media_type, nombre_de_archivo)` del reporte pedido."""
    tablas: list[Tabla] = []
    if tipo in (TipoReporte.CONSOLIDADO, TipoReporte.ROTACION):
        tablas.append(_tabla_rotacion(rotacion_e_indice_quiebres(db, desde, hasta, ruta_id)))
    if tipo in (TipoReporte.CONSOLIDADO, TipoReporte.COMISIONES):
        # Sin periodo explícito el consolidado liquida el mes del último dato.
        comisiones = liquidacion_comisiones(db, periodo_desde, periodo_hasta, None, ruta_id)
        tablas.append(_tabla_comisiones(comisiones))
    if tipo in (TipoReporte.CONSOLIDADO, TipoReporte.VENTAS_PROYECCION):
        tablas.append(_tabla_ventas(ventas_vs_proyeccion(db, desde, hasta, ruta_id)))

    if formato is FormatoReporte.XLSX:
        contenido, media_type = report_export.a_xlsx(tablas), report_export.MEDIA_TYPE_XLSX
    else:
        contenido, media_type = report_export.a_csv(tablas), report_export.MEDIA_TYPE_CSV
    return contenido, media_type, f"reporte_{tipo.value}_{date.today():%Y%m%d}.{formato.value}"
