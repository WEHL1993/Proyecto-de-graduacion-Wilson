"""Caso de uso: inferencia de demanda con el modelo en `produccion` (TC-PRED-01/02/03).

Carga el modelo productivo (caché en memoria + validación SHA-256), pronostica cada serie
(producto, ruta) y agrega por producto: la demanda agregada es la suma de rutas y su intervalo
combina las semi-amplitudes por raíz de la suma de cuadrados (rutas independientes).
"""

import math
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.ml import contracts
from app.repositories import catalog_repo, forecast_repo, model_repo, sales_repo
from app.schemas.predictions import (
    DemandModelInfo,
    DemandPoint,
    DemandProductForecast,
    DemandRequest,
    DemandResponse,
)


def predecir_demanda(db: Session, solicitud: DemandRequest) -> DemandResponse:
    settings = get_settings()
    modelo = model_repo.obtener_produccion(db, settings.ml_modelo_nombre)
    if modelo is None:
        raise AppError(
            "SIN_MODELO_PRODUCTIVO",
            "No hay un modelo en estado `produccion`; entrene y promueva uno primero.",
        )

    producto_ids = list(dict.fromkeys(solicitud.producto_ids))
    _validar_catalogo(db, producto_ids, solicitud.ruta_id)

    try:
        predictor = contracts.cargar_predictor(
            modelo_id=modelo.id,
            raiz=settings.ml_artifacts_dir,
            ruta_relativa=modelo.ruta_artefacto,
            hash_artefacto=modelo.hash_artefacto,
            esquema_features=modelo.esquema_features,
        )
    except contracts.ArtefactoNoEncontrado as exc:
        raise AppError("ARTEFACTO_NO_ENCONTRADO", str(exc), status_code=500) from exc
    except contracts.ArtefactoCorrupto as exc:
        raise AppError("ARTEFACTO_CORRUPTO", str(exc), status_code=500) from exc

    fecha_base = solicitud.fecha_base or date.today()
    historial = _cargar_historial(db, producto_ids, solicitud.ruta_id, fecha_base)
    sin_historia = {str(p) for p in producto_ids} - set(historial["producto_id"])
    if sin_historia:
        raise _historial_insuficiente(sorted(sin_historia))
    try:
        puntos = predictor.predecir(historial, fecha_base, solicitud.horizonte_dias)
    except contracts.HistorialInsuficiente as exc:
        raise _historial_insuficiente(exc.productos, exc.dias_minimos) from exc

    series = _agregar_por_producto(puntos)
    generado_en = datetime.now(UTC)
    pronosticos = [
        DemandProductForecast(
            producto_id=producto_id,
            serie=[
                DemandPoint(
                    fecha_objetivo=p.fecha_objetivo,
                    demanda_predicha=p.demanda,
                    limite_inferior=p.inferior if solicitud.incluir_intervalo else None,
                    limite_superior=p.superior if solicitud.incluir_intervalo else None,
                )
                for p in serie
            ],
        )
        for producto_id, serie in ((uuid.UUID(k), v) for k, v in series.items())
    ]

    if solicitud.persistir:
        forecast_repo.upsert_pronosticos(
            db,
            [
                {
                    "modelo_id": modelo.id,
                    "producto_id": producto_id,
                    "ruta_id": solicitud.ruta_id,
                    "fecha_objetivo": p.fecha_objetivo,
                    "horizonte_dias": p.horizonte_dias,
                    "demanda_predicha": Decimal(str(p.demanda)),
                    "limite_inferior": Decimal(str(p.inferior))
                    if solicitud.incluir_intervalo
                    else None,
                    "limite_superior": Decimal(str(p.superior))
                    if solicitud.incluir_intervalo
                    else None,
                    "generado_en": generado_en,
                }
                for producto_id, serie in ((uuid.UUID(k), v) for k, v in series.items())
                for p in serie
            ],
        )
        db.commit()

    return DemandResponse(
        modelo=DemandModelInfo(id=modelo.id, algoritmo=modelo.algoritmo, version=modelo.version),
        generado_en=generado_en,
        pronosticos=pronosticos,
    )


def _validar_catalogo(
    db: Session, producto_ids: list[uuid.UUID], ruta_id: uuid.UUID | None
) -> None:
    faltantes = set(producto_ids) - catalog_repo.productos_existentes(db, producto_ids)
    if faltantes:
        raise AppError(
            "PRODUCTO_NO_ENCONTRADO",
            "Uno o más productos no existen en el catálogo.",
            detalle={"producto_ids": sorted(str(p) for p in faltantes)},
        )
    if ruta_id is not None and not catalog_repo.ruta_existe(db, ruta_id):
        raise AppError("RUTA_NO_ENCONTRADA", "La ruta indicada no existe.")


def _cargar_historial(
    db: Session, producto_ids: list[uuid.UUID], ruta_id: uuid.UUID | None, hasta: date
) -> pd.DataFrame:
    filas = sales_repo.ventas_diarias(db, hasta=hasta, producto_ids=producto_ids, ruta_id=ruta_id)
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime([f[0] for f in filas]),
            "producto_id": [str(f[1]) for f in filas],
            "ruta_id": [str(f[2]) for f in filas],
            "cantidad": [float(f[3]) for f in filas],
        }
    )


def _historial_insuficiente(productos: list[str], dias_minimos: int | None = None) -> AppError:
    return AppError(
        "HISTORIAL_INSUFICIENTE",
        "No hay historial de ventas suficiente para pronosticar los productos indicados.",
        detalle={"producto_ids": productos, "dias_minimos": dias_minimos},
    )


def _agregar_por_producto(
    puntos: list[contracts.PuntoPronostico],
) -> dict[str, list[contracts.PuntoPronostico]]:
    """Suma las rutas por (producto, fecha) y redondea a 2 decimales (numeric(12,2))."""
    grupos: dict[tuple[str, date], list[contracts.PuntoPronostico]] = defaultdict(list)
    for p in puntos:
        grupos[(p.producto_id, p.fecha_objetivo)].append(p)

    salida: dict[str, list[contracts.PuntoPronostico]] = defaultdict(list)
    for (producto_id, fecha), grupo in sorted(grupos.items()):
        demanda = sum(p.demanda for p in grupo)
        mitad_inf = math.sqrt(sum((p.demanda - p.inferior) ** 2 for p in grupo))
        mitad_sup = math.sqrt(sum((p.superior - p.demanda) ** 2 for p in grupo))
        salida[producto_id].append(
            contracts.PuntoPronostico(
                producto_id=producto_id,
                ruta_id="*",
                fecha_objetivo=fecha,
                horizonte_dias=grupo[0].horizonte_dias,
                demanda=round(demanda, 2),
                inferior=round(max(0.0, demanda - mitad_inf), 2),
                superior=round(demanda + mitad_sup, 2),
            )
        )
    return salida
