"""Caso de uso: entrenar, evaluar y registrar un modelo de demanda (motivo `manual`/`programado`).

El modelo queda como `candidato`; solo pasa a `produccion` con `promover=True` (ADR-03).

ADR-14 (política de datos): el **entrenamiento inicial** usa los Excel (`excel_historico`, sin
cambios). Los **reentrenamientos** usan lo que indique `ml.fuente_reentrenamiento`: la base Excel
congelada más lo liquidado (`excel_mas_liquidacion`) o solo lo liquidado. Con liquidaciones el
calendario solo se completa con ceros dentro de los rangos efectivamente cubiertos de cada ruta
(un hueco entre la base y la primera liquidación no es demanda cero) y las observaciones con
`agotado` (demanda censurada: la venta es un piso) pesan menos en el entrenamiento.
"""

import uuid
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import FuenteReentrenamiento, MotivoEntrenamiento, OrigenDatos
from app.domain.models.ml import ModeloML
from app.ml import contracts
from app.repositories import liquidacion_repo, sales_repo
from app.services.bitacora_service import auditar

# Historia mínima por ruta para entrenar solo con liquidaciones (días contiguos de rezagos).
DIAS_MINIMOS_LIQUIDADOS = 28


@auditar
def entrenar_modelo(
    db: Session,
    *,
    algoritmo: str,
    hiperparametros: dict | None = None,
    motivo: MotivoEntrenamiento = MotivoEntrenamiento.MANUAL,
    entrenado_por: uuid.UUID | None = None,
    promover: bool = False,
    ventana_desde: date | None = None,
    ventana_hasta: date | None = None,
    fuente: FuenteReentrenamiento = FuenteReentrenamiento.EXCEL_HISTORICO,
) -> ModeloML:
    settings = get_settings()
    ventas, cobertura, fuentes_datos = _preparar_datos(db, fuente, ventana_desde, ventana_hasta)
    try:
        resultado = contracts.entrenar_y_evaluar(ventas, algoritmo, hiperparametros, cobertura)
    except contracts.HistorialInsuficiente as exc:
        raise AppError(
            "HISTORIAL_INSUFICIENTE",
            f"{exc} Con liquidaciones el último tramo necesita además los días del holdout.",
            detalle={"dias_minimos": exc.dias_minimos, "producto_ids": exc.productos},
        ) from exc
    except contracts.DatosInsuficientes as exc:
        raise AppError("DATOS_INSUFICIENTES", str(exc)) from exc
    except ValueError as exc:  # algoritmo no soportado
        raise AppError("ALGORITMO_NO_SOPORTADO", str(exc)) from exc

    fuentes_datos["observaciones_censuradas"] = resultado.informe.get(
        "n_observaciones_censuradas", 0
    )
    modelo = contracts.registrar_modelo(
        db,
        nombre=settings.ml_modelo_nombre,
        algoritmo=algoritmo,
        resultado=resultado,
        motivo=motivo.value,
        entrenado_por=entrenado_por,
        raiz_artefactos=settings.ml_artifacts_dir,
        fuentes_datos=fuentes_datos,
    )
    if promover:
        contracts.promover_a_produccion(db, modelo.id)
    db.commit()
    return modelo


def _preparar_datos(
    db: Session, fuente: FuenteReentrenamiento, desde: date | None, hasta: date | None
) -> tuple[pd.DataFrame, dict[str, list[tuple[date, date]]] | None, dict[str, Any]]:
    """`(ventas, cobertura, trazabilidad)`. Sin liquidaciones cerradas el comportamiento es el
    clásico (todo `ventas_historicas`, calendario contiguo) y `cobertura` es `None`."""
    rangos_liquidados = liquidacion_repo.rangos_cerrados_por_ruta(db)
    usa_liquidacion = fuente != FuenteReentrenamiento.EXCEL_HISTORICO

    if fuente == FuenteReentrenamiento.LIQUIDACION:
        _exigir_historia_liquidada(rangos_liquidados)
    if not usa_liquidacion or not rangos_liquidados:
        origenes = None if usa_liquidacion else [OrigenDatos.EXCEL_HISTORICO]
        filas = sales_repo.ventas_diarias(db, desde=desde, hasta=hasta, origenes=origenes)
        return _marco(filas), None, _trazabilidad(db, fuente, origenes)

    origenes = (
        [OrigenDatos.LIQUIDACION]
        if fuente == FuenteReentrenamiento.LIQUIDACION
        else [OrigenDatos.EXCEL_HISTORICO, OrigenDatos.LIQUIDACION]
    )
    filas = sales_repo.ventas_diarias(db, desde=desde, hasta=hasta, origenes=origenes)
    ventas = _marco(filas)

    # Cobertura por ruta: rango de la base Excel (si entra) + rango liquidado.
    cobertura: dict[str, list[tuple[date, date]]] = {}
    if OrigenDatos.EXCEL_HISTORICO in origenes:
        for ruta, rango in sales_repo.rangos_por_ruta_de_origen(
            db, OrigenDatos.EXCEL_HISTORICO
        ).items():
            cobertura.setdefault(str(ruta), []).append(rango)
    for ruta, rango in rangos_liquidados.items():
        cobertura.setdefault(str(ruta), []).append(rango)

    censuras = liquidacion_repo.censuras(db)
    ventas["censurada"] = [
        1.0 if (f, uuid.UUID(p), uuid.UUID(r)) in censuras else 0.0
        for f, p, r in zip(
            ventas["fecha"].dt.date, ventas["producto_id"], ventas["ruta_id"], strict=True
        )
    ]
    return ventas, cobertura, _trazabilidad(db, fuente, origenes)


def _exigir_historia_liquidada(rangos: dict[uuid.UUID, tuple[date, date]]) -> None:
    """Solo con liquidaciones: cada ruta liquidada necesita al menos `DIAS_MINIMOS_LIQUIDADOS`."""
    cortas = {
        str(ruta): (hasta - desde).days + 1
        for ruta, (desde, hasta) in rangos.items()
        if (hasta - desde).days + 1 < DIAS_MINIMOS_LIQUIDADOS
    }
    if not rangos or cortas:
        raise AppError(
            "HISTORIAL_INSUFICIENTE",
            f"Se requieren al menos {DIAS_MINIMOS_LIQUIDADOS} días liquidados por ruta para "
            "entrenar solo con liquidaciones.",
            detalle={"dias_minimos": DIAS_MINIMOS_LIQUIDADOS, "rutas_con_menos_dias": cortas},
        )


def _marco(filas: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime([f[0] for f in filas]),
            "producto_id": [str(f[1]) for f in filas],
            "ruta_id": [str(f[2]) for f in filas],
            "cantidad": [float(f[3]) for f in filas],
        }
    )


def _trazabilidad(
    db: Session, fuente: FuenteReentrenamiento, origenes: list[OrigenDatos] | None
) -> dict[str, Any]:
    """Fuente y filas/rango por origen usados (se guarda en `modelos_ml.fuentes_datos`)."""
    resumen = sales_repo.resumen_por_origen(db)
    usados = {o.value for o in origenes} if origenes is not None else set(resumen)
    return {
        "fuente": fuente.value,
        "origenes": {
            origen: {
                "filas": datos["filas"],
                "desde": datos["desde"].isoformat(),
                "hasta": datos["hasta"].isoformat(),
            }
            for origen, datos in resumen.items()
            if origen in usados
        },
        "dias_liquidados": liquidacion_repo.dias_cerrados(db),
    }
