"""Sincroniza los artefactos en disco con `modelos_ml` / `metricas_evaluacion` y aplica ADR-03
(exactamente un modelo en `produccion` por familia)."""

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import EstadoModelo
from app.domain.models.ml import ModeloML
from app.ml.contracts import ResultadoEntrenamiento
from app.ml.registry import artifact_store
from app.repositories import model_repo


def registrar_modelo(
    db: Session,
    *,
    nombre: str,
    algoritmo: str,
    resultado: ResultadoEntrenamiento,
    motivo: str,
    entrenado_por: uuid.UUID | None,
    raiz_artefactos: Path,
    fuentes_datos: dict | None = None,
) -> ModeloML:
    """Guarda los artefactos y registra el modelo como `candidato` con sus métricas."""
    version = model_repo.siguiente_version(db, nombre)
    guardado = artifact_store.guardar_artefactos(
        raiz_artefactos,
        algoritmo=algoritmo,
        version=version,
        modelo=resultado.modelo,
        preprocesador=resultado.preprocesador,
        informe={**resultado.informe, "nombre": nombre, "version": version},
    )
    modelo = model_repo.crear(
        db,
        nombre=nombre,
        algoritmo=algoritmo,
        version=version,
        estado=EstadoModelo.CANDIDATO,
        ruta_artefacto=guardado.ruta_relativa,
        hash_artefacto=guardado.hash_modelo,
        hiperparametros=resultado.hiperparametros,
        esquema_features=guardado.esquema_features,
        ventana_desde=resultado.ventana_desde,
        ventana_hasta=resultado.ventana_hasta,
        motivo_entrenamiento=motivo,
        entrenado_por=entrenado_por,
        fuentes_datos=fuentes_datos,
    )
    model_repo.registrar_metricas(
        db,
        [
            {
                "modelo_id": modelo.id,
                "producto_id": uuid.UUID(m.producto_id) if m.producto_id else None,
                "tipo_evaluacion": m.tipo_evaluacion.value,
                "mae": round(m.metricas.mae, 4),
                "rmse": round(m.metricas.rmse, 4),
                "mape": None if m.metricas.mape is None else round(m.metricas.mape, 3),
                "n_muestras": m.metricas.n_muestras,
                "periodo_desde": m.periodo_desde,
                "periodo_hasta": m.periodo_hasta,
            }
            for m in resultado.metricas
        ],
    )
    return modelo


def promover_a_produccion(db: Session, modelo_id: uuid.UUID) -> ModeloML:
    """Archiva el modelo vigente de la familia y promueve `modelo_id` en la misma transacción."""
    modelo = model_repo.obtener(db, modelo_id, bloquear=True)
    if modelo is None:
        raise AppError("MODELO_NO_ENCONTRADO", "El modelo no existe.", status_code=404)
    if modelo.estado == EstadoModelo.PRODUCCION:
        return modelo
    if modelo.estado == EstadoModelo.DESCARTADO:
        raise AppError("TRANSICION_INVALIDA", "Un modelo descartado no puede promoverse.")
    model_repo.archivar_produccion_de(db, modelo.nombre, excepto=modelo.id)
    model_repo.marcar_produccion(db, modelo)
    return modelo
