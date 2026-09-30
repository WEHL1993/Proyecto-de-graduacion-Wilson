"""Caso de uso ETL: ingesta de histórico de ventas desde Excel (TC-ETL-01..04).

Flujo: checksum SHA-256 -> duplicado (400) -> lectura -> validación contra catálogo ->
rechazo (422, lote `rechazado` + alerta `etl_error`) o carga idempotente en
`ventas_historicas` + cálculo de `comisiones`. El servicio hace `commit` explícito.
"""

import hashlib
import re
import uuid
from collections import defaultdict
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoLoteEtl, Severidad, TipoAlerta
from app.domain.models.sales import EtlLote
from app.repositories import alert_repo, catalog_repo, parametro_repo, sales_repo, user_repo
from app.schemas.etl import (
    MAX_ERRORES_DETALLADOS,
    TAMANO_MAXIMO_BYTES,
    CodigoErrorEtl,
    ErrorFila,
    EtlResult,
    EtlValidationError,
    LoteItem,
    LotePage,
    ModoCarga,
    RangoFechas,
)
from app.services import etl_lectura
from app.services.etl_lectura import ArchivoInvalido, ErrorLectura, FilaVenta, LecturaExcel

PARAMETRO_COMISION = "comisiones.porcentaje"
_RE_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CENTAVOS = Decimal("0.01")
_MILESIMAS = Decimal("0.001")
_LARGO_MAX_VALOR = 200

_ClaveVenta = tuple[Any, ...]  # (fecha, producto_id, ruta_id, vendedor_id)


def calcular_checksum(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def procesar_excel(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    nombre_archivo: str,
    contenido: bytes,
    modo: ModoCarga = ModoCarga.ESTRICTO,
    hoja: str | None = None,
    periodo: str | None = None,
) -> EtlResult | EtlValidationError:
    """Devuelve `EtlResult` (lote cargado) o `EtlValidationError` (lote rechazado, HTTP 422).

    Lanza `AppError` 400 para archivo inválido/duplicado; la API traduce ambos casos.
    """
    _validar_archivo(nombre_archivo, contenido, periodo)
    checksum = calcular_checksum(contenido)

    previo = sales_repo.obtener_lote_por_checksum(db, checksum)
    if previo is not None and previo.estado != EstadoLoteEtl.RECHAZADO:
        raise _lote_duplicado(previo)

    try:
        lectura = etl_lectura.leer_excel(
            contenido, nombre_archivo=nombre_archivo, hoja=hoja, periodo=periodo
        )
    except ArchivoInvalido as exc:
        raise AppError(exc.codigo, exc.mensaje) from exc

    lote = _preparar_lote(db, previo, usuario_id, nombre_archivo, checksum)

    errores, ventas, filas_rechazadas, advertencias = _validar(db, lectura)
    filas_validas = max(lectura.filas_totales - filas_rechazadas, 0)
    if lectura.columnas_faltantes:
        filas_validas, filas_rechazadas = 0, lectura.filas_totales

    if lectura.filas_totales == 0 and not errores:
        errores.append(
            ErrorLectura(
                fila=1,
                columna="*",
                mensaje="El archivo no contiene filas de datos.",
                categoria=CodigoErrorEtl.DATOS_INVALIDOS,
            )
        )

    rechazar = (
        bool(lectura.columnas_faltantes)
        or (bool(errores) and modo == ModoCarga.ESTRICTO)
        or not ventas
    )
    if rechazar:
        return _rechazar(db, lote, lectura, errores, filas_validas, filas_rechazadas)

    return _cargar(
        db, lote, lectura, errores, ventas, filas_validas, filas_rechazadas, advertencias
    )


# ------------------------------------------------------------------ validaciones de entrada
def _validar_archivo(nombre_archivo: str, contenido: bytes, periodo: str | None) -> None:
    if not nombre_archivo.lower().endswith(".xlsx"):
        raise AppError("ARCHIVO_INVALIDO", "Solo se admiten archivos .xlsx.")
    if not contenido:
        raise AppError("ARCHIVO_INVALIDO", "El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise AppError("ARCHIVO_INVALIDO", "El archivo supera el máximo de 20 MB.")
    if periodo is not None and not _RE_PERIODO.match(periodo):
        raise AppError("PERIODO_INVALIDO", "El periodo debe tener el formato YYYY-MM.")


def _lote_duplicado(lote: EtlLote) -> AppError:
    return AppError(
        "LOTE_DUPLICADO",
        "Este archivo ya fue procesado (mismo checksum SHA-256).",
        detalle={"lote_id": str(lote.id), "estado": lote.estado},
    )


def _preparar_lote(
    db: Session, previo: EtlLote | None, usuario_id: uuid.UUID, nombre: str, checksum: str
) -> EtlLote:
    """Un lote `rechazado` no cargó nada: se reprocesa el mismo archivo reutilizando su fila
    (el `checksum` es único). Ej.: se rechazó por SKU faltantes y luego se cargó el catálogo."""
    if previo is not None:
        previo.usuario_id = usuario_id
        previo.archivo_nombre = nombre
        previo.estado = EstadoLoteEtl.RECIBIDO
        return previo
    try:
        return sales_repo.crear_lote(
            db, usuario_id=usuario_id, archivo_nombre=nombre, checksum=checksum
        )
    except IntegrityError as exc:  # carrera con otra carga del mismo archivo
        db.rollback()
        raise AppError(
            "LOTE_DUPLICADO", "Este archivo ya fue procesado (mismo checksum SHA-256)."
        ) from exc


# ------------------------------------------------------------------ validación contra catálogo
def _validar(
    db: Session, lectura: LecturaExcel
) -> tuple[list[ErrorLectura], dict[_ClaveVenta, dict[str, Any]], int, list[str]]:
    """Resuelve SKU/ruta/vendedor a ids y agrega duplicados de la misma clave de negocio.

    Devuelve (errores, ventas por clave, filas rechazadas, advertencias).
    """
    errores = list(lectura.errores)
    rechazados = set(lectura.filas_con_error)
    advertencias = list(lectura.advertencias)

    productos = catalog_repo.mapear_skus(db, {f.sku for f in lectura.filas})
    rutas = catalog_repo.mapear_rutas(db, {f.ruta for f in lectura.filas})
    vendedores = user_repo.mapear_por_identificador(
        db, {f.vendedor for f in lectura.filas if f.vendedor}
    )

    agrupar = lectura.formato == etl_lectura.FORMATO_ANCHO
    vistos: dict[tuple[str | None, str, str | None], int] = {}
    ventas: dict[_ClaveVenta, dict[str, Any]] = {}
    duplicadas = 0

    def reportar(fila: FilaVenta, columna: str, valor: str, mensaje: str) -> None:
        rechazados.add((fila.hoja, fila.fila, fila.registro))
        clave = (fila.hoja, columna, valor)
        if agrupar and clave in vistos:  # un error por hoja/valor, no uno por celda
            vistos[clave] += 1
            return
        vistos[clave] = 1
        errores.append(
            ErrorLectura(
                fila=fila.fila,
                columna=columna,
                mensaje=mensaje,
                categoria=CodigoErrorEtl.DATOS_INVALIDOS,
                valor=valor,
                hoja=fila.hoja,
                registro=fila.registro,
            )
        )

    for fila in lectura.filas:
        producto_id = productos.get(fila.sku.upper())
        ruta = rutas.get(fila.ruta.lower())
        vendedor_id = None
        if producto_id is None:
            reportar(fila, "sku", fila.sku, f"El producto '{fila.sku}' no existe en el catálogo.")
        if ruta is None:
            columna = "hoja" if agrupar else "ruta"
            reportar(fila, columna, fila.ruta, f"La ruta '{fila.ruta}' no está registrada.")
        elif fila.vendedor:
            vendedor_id = vendedores.get(fila.vendedor.lower())
            if vendedor_id is None:
                reportar(
                    fila, "vendedor", fila.vendedor, f"El vendedor '{fila.vendedor}' no existe."
                )
        else:
            vendedor_id = ruta.vendedor_id
        if producto_id is None or ruta is None or (fila.vendedor and vendedor_id is None):
            continue

        clave = (fila.fecha, producto_id, ruta.id, vendedor_id)
        acumulado = ventas.get(clave)
        if acumulado is None:
            ventas[clave] = {
                "cantidad": fila.cantidad,
                "monto": fila.monto_total,
                "precio": fila.precio_unitario,
                "n": 1,
            }
        else:
            duplicadas += 1
            acumulado["cantidad"] += fila.cantidad
            acumulado["monto"] += fila.monto_total
            acumulado["n"] += 1

    # `agrupar` resume errores repetidos: se indica cuántos registros afecta cada uno.
    if agrupar:
        errores = [_con_conteo(e, vistos) for e in errores]
    if duplicadas:
        advertencias.append(
            f"{duplicadas} filas repetían fecha/producto/ruta/vendedor y se sumaron en un registro."
        )
    errores.sort(key=lambda e: (e.hoja or "", e.fila))
    return errores, ventas, len(rechazados), advertencias


def _con_conteo(
    error: ErrorLectura, vistos: dict[tuple[str | None, str, str | None], int]
) -> ErrorLectura:
    total = vistos.get((error.hoja, error.columna, error.valor or ""), 1)
    if total > 1:
        return replace(error, mensaje=f"{error.mensaje} ({total} registros afectados)")
    return error


# ------------------------------------------------------------------ desenlaces
def _serializar_errores(errores: list[ErrorLectura]) -> list[ErrorFila]:
    return [
        ErrorFila(
            fila=e.fila,
            columna=e.columna,
            valor=None if e.valor is None else e.valor[:_LARGO_MAX_VALOR],
            mensaje=e.mensaje,
            hoja=e.hoja,
        )
        for e in errores[:MAX_ERRORES_DETALLADOS]
    ]


def _codigo_error(errores: list[ErrorLectura]) -> CodigoErrorEtl:
    categorias = {e.categoria for e in errores}
    if CodigoErrorEtl.COLUMNAS_FALTANTES in categorias:
        return CodigoErrorEtl.COLUMNAS_FALTANTES
    if categorias == {CodigoErrorEtl.TIPOS_INVALIDOS}:
        return CodigoErrorEtl.TIPOS_INVALIDOS
    return CodigoErrorEtl.DATOS_INVALIDOS


def _rechazar(
    db: Session,
    lote: EtlLote,
    lectura: LecturaExcel,
    errores: list[ErrorLectura],
    filas_validas: int,
    filas_rechazadas: int,
) -> EtlValidationError:
    detallados = _serializar_errores(errores)
    codigo = _codigo_error(errores)
    sales_repo.actualizar_lote(
        lote,
        estado=EstadoLoteEtl.RECHAZADO,
        filas_totales=lectura.filas_totales,
        filas_validas=filas_validas,
        filas_rechazadas=filas_rechazadas,
        errores=[e.model_dump(exclude_none=True) for e in detallados],
    )
    alert_repo.crear(
        db,
        tipo=TipoAlerta.ETL_ERROR,
        severidad=Severidad.ADVERTENCIA,
        mensaje=(
            f"Carga '{lote.archivo_nombre}' rechazada ({codigo}): {len(errores)} errores "
            f"en {filas_rechazadas} de {lectura.filas_totales} filas. Lote {lote.id}."
        ),
    )
    db.commit()
    return EtlValidationError(
        codigo=codigo, lote_id=lote.id, errores=detallados, total_errores=len(errores)
    )


def _cargar(
    db: Session,
    lote: EtlLote,
    lectura: LecturaExcel,
    errores: list[ErrorLectura],
    ventas: dict[_ClaveVenta, dict[str, Any]],
    filas_validas: int,
    filas_rechazadas: int,
    advertencias: list[str],
) -> EtlResult:
    filas_db = []
    for (fecha, producto_id, ruta_id, vendedor_id), v in ventas.items():
        precio = v["precio"]
        if v["n"] > 1 and v["cantidad"] > 0:  # duplicados sumados: precio medio ponderado
            precio = (v["monto"] / v["cantidad"]).quantize(_CENTAVOS, ROUND_HALF_UP)
        filas_db.append(
            {
                "lote_id": lote.id,
                "fecha_venta": fecha,
                "producto_id": producto_id,
                "ruta_id": ruta_id,
                "vendedor_id": vendedor_id,
                "cantidad": v["cantidad"],
                "precio_unitario": precio,
                "monto_total": v["monto"],
            }
        )

    persistidas = sales_repo.upsert_ventas(db, filas_db)
    advertencias.extend(_generar_comisiones(db, persistidas))

    if errores:
        advertencias.append(
            f"{filas_rechazadas} filas rechazadas (carga parcial); detalle en el lote {lote.id}."
        )
    sales_repo.actualizar_lote(
        lote,
        estado=EstadoLoteEtl.CARGADO,
        filas_totales=lectura.filas_totales,
        filas_validas=filas_validas,
        filas_rechazadas=filas_rechazadas,
        errores=[e.model_dump(exclude_none=True) for e in _serializar_errores(errores)] or None,
    )
    db.commit()

    fechas = [f["fecha_venta"] for f in filas_db]
    return EtlResult(
        lote_id=lote.id,
        estado="cargado",
        filas_totales=lectura.filas_totales,
        filas_validas=filas_validas,
        filas_rechazadas=filas_rechazadas,
        rango_fechas=RangoFechas(desde=min(fechas), hasta=max(fechas)),
        advertencias=advertencias,
    )


def _generar_comisiones(db: Session, ventas: list[sales_repo.VentaPersistida]) -> list[str]:
    """`monto = monto_total × porcentaje / 100` por venta con vendedor (idempotente)."""
    valor = parametro_repo.obtener_valor(db, PARAMETRO_COMISION)
    if valor is None:
        return [f"Parámetro '{PARAMETRO_COMISION}' no configurado: no se generaron comisiones."]
    try:
        porcentaje = Decimal(str(valor)).quantize(_MILESIMAS, ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        porcentaje = Decimal(-1)
    if not Decimal(0) <= porcentaje <= Decimal(100):
        return [f"Parámetro '{PARAMETRO_COMISION}' inválido ({valor!r}): sin comisiones."]

    por_periodo: dict[str, int] = defaultdict(int)
    filas = []
    for venta in ventas:
        if venta.vendedor_id is None:
            continue
        periodo = venta.fecha_venta.strftime("%Y-%m")
        por_periodo[periodo] += 1
        filas.append(
            {
                "vendedor_id": venta.vendedor_id,
                "venta_id": venta.id,
                "periodo": periodo,
                "porcentaje": porcentaje,
                "monto": (venta.monto_total * porcentaje / 100).quantize(_CENTAVOS, ROUND_HALF_UP),
            }
        )
    sales_repo.upsert_comisiones(db, filas)

    sin_vendedor = len(ventas) - len(filas)
    if sin_vendedor:
        return [f"{sin_vendedor} ventas sin vendedor no generaron comisión."]
    return []


def listar_lotes(db: Session, *, estado: EstadoLoteEtl | None, limit: int, offset: int) -> LotePage:
    filas, total = sales_repo.listar_lotes(db, estado=estado, limit=limit, offset=offset)
    return LotePage(
        total=total,
        lotes=[
            LoteItem(
                id=lote.id,
                archivo_nombre=lote.archivo_nombre,
                estado=lote.estado,
                filas_totales=lote.filas_totales,
                filas_validas=lote.filas_validas,
                filas_rechazadas=lote.filas_rechazadas,
                cargado_por=nombre,
                creado_en=lote.creado_en,
            )
            for lote, nombre in filas
        ],
    )
