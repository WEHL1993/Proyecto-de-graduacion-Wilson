"""Caso de uso: monitoreo de precisión y degradación del modelo productivo (ADR-08, ADR-12).

`evaluar_produccion` cruza `pronosticos_demanda` con las ventas reales por **periodos
consecutivos y sin traslape** de `PERIODO_DIAS` días, guarda MAE/RMSE/MAPE en
`metricas_evaluacion` (tipo `produccion`) y, si el MAPE supera el umbral durante N periodos
consecutivos, crea la alerta crítica `mape_umbral` y encola un reentrenamiento
(`motivo=degradacion`). Cubre TC-ML-01, TC-MET-01 y TC-MET-02.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.domain.enums import (
    MotivoEntrenamiento,
    Severidad,
    TipoAlerta,
    TipoEvaluacion,
    TipoJob,
)
from app.domain.models.ml import MetricaEvaluacion, ModeloML
from app.ml import contracts
from app.repositories import (
    alert_repo,
    catalog_repo,
    forecast_repo,
    job_repo,
    model_repo,
    parametro_repo,
    sales_repo,
)
from app.schemas.ml import (
    Degradacion,
    MetricPoint,
    MetricsResponse,
    MlConfig,
    ModeloInfo,
    ModeloResumen,
    PeorProducto,
    ResumenMetricas,
)

PERIODO_DIAS = 7
CLAVE_UMBRAL = "ml.mape_umbral"
CLAVE_PERIODOS = "ml.periodos_consecutivos"
UMBRAL_POR_DEFECTO = 12.0
PERIODOS_POR_DEFECTO = 3

_MAX_PERIODOS_POR_EJECUCION = 52
_TOP_PEORES_PRODUCTOS = 10
_TOLERANCIA_TENDENCIA = 0.5  # puntos porcentuales de MAPE


@dataclass(frozen=True)
class PeriodoEvaluado:
    desde: date
    hasta: date
    mape: float | None
    mae: float
    rmse: float
    n_muestras: int
    supera_umbral: bool


@dataclass
class ResultadoEvaluacion:
    estado: Literal["evaluado", "sin_modelo_productivo", "sin_datos"]
    modelo_id: uuid.UUID | None = None
    periodos: list[PeriodoEvaluado] = field(default_factory=list)
    periodos_consecutivos: int = 0
    degradacion_detectada: bool = False
    alerta_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


# ------------------------------------------------------------------ configuración (ADR-08)
def obtener_config(db: Session) -> MlConfig:
    umbral = parametro_repo.obtener_valor(db, CLAVE_UMBRAL)
    periodos = parametro_repo.obtener_valor(db, CLAVE_PERIODOS)
    return MlConfig(
        umbral_mape=float(umbral) if isinstance(umbral, int | float) else UMBRAL_POR_DEFECTO,
        periodos_consecutivos=(
            int(periodos) if isinstance(periodos, int | float) else PERIODOS_POR_DEFECTO
        ),
    )


def actualizar_config(db: Session, config: MlConfig, usuario_id: uuid.UUID) -> MlConfig:
    parametro_repo.guardar_valor(db, CLAVE_UMBRAL, config.umbral_mape, actualizado_por=usuario_id)
    parametro_repo.guardar_valor(
        db, CLAVE_PERIODOS, config.periodos_consecutivos, actualizado_por=usuario_id
    )
    db.commit()
    return config


# ------------------------------------------------------------------ evaluación (Worker)
def evaluar_produccion(
    db: Session, *, desde: date | None = None, hasta: date | None = None
) -> ResultadoEvaluacion:
    """Evalúa los periodos pendientes (o `[desde, hasta]` si se indica) del modelo productivo."""
    modelo = model_repo.obtener_produccion(db, get_settings().ml_modelo_nombre)
    if modelo is None:
        return ResultadoEvaluacion(estado="sin_modelo_productivo")

    config = obtener_config(db)
    if desde is not None and hasta is not None:
        _completar_demanda_real(db, modelo.id, desde, hasta)
        periodos = [(desde, hasta)]
    else:
        periodos = _periodos_pendientes(db, modelo)

    evaluados = [
        p
        for d, h in periodos
        if (p := _evaluar_periodo(db, modelo, d, h, config.umbral_mape)) is not None
    ]
    if not evaluados:
        db.commit()
        return ResultadoEvaluacion(estado="sin_datos", modelo_id=modelo.id)

    resultado = ResultadoEvaluacion(estado="evaluado", modelo_id=modelo.id, periodos=evaluados)
    resultado.periodos_consecutivos = _consecutivos_sobre_umbral(db, modelo.id)
    if resultado.periodos_consecutivos >= config.periodos_consecutivos:
        resultado.degradacion_detectada = True
        resultado.alerta_id = _alertar_degradacion(db, modelo, config, resultado)
        resultado.job_id = _encolar_reentrenamiento(db, modelo)
    db.commit()
    return resultado


def _completar_demanda_real(db: Session, modelo_id: uuid.UUID, desde: date, hasta: date) -> None:
    ventas_hasta = sales_repo.ultima_fecha_venta(db)
    if ventas_hasta is not None:
        forecast_repo.registrar_demanda_real(db, modelo_id, desde, hasta, ventas_hasta=ventas_hasta)


def _periodos_pendientes(db: Session, modelo: ModeloML) -> list[tuple[date, date]]:
    """Periodos completos de `PERIODO_DIAS` con demanda real, posteriores al último evaluado."""
    ultimo = model_repo.ultimo_periodo_evaluado(db, modelo.id, TipoEvaluacion.PRODUCCION)
    inicio = (
        ultimo + timedelta(days=1)
        if ultimo is not None
        else forecast_repo.primera_fecha_objetivo(db, modelo.id)
    )
    if inicio is None:
        return []
    ventas_hasta = sales_repo.ultima_fecha_venta(db)
    if ventas_hasta is not None:
        forecast_repo.registrar_demanda_real(
            db, modelo.id, inicio, ventas_hasta, ventas_hasta=ventas_hasta
        )
    ultima_real = forecast_repo.ultima_fecha_con_real(db, modelo.id)
    if ultima_real is None:
        return []
    periodos: list[tuple[date, date]] = []
    desde = inicio
    while desde + timedelta(days=PERIODO_DIAS - 1) <= ultima_real:
        if len(periodos) >= _MAX_PERIODOS_POR_EJECUCION:
            break
        periodos.append((desde, desde + timedelta(days=PERIODO_DIAS - 1)))
        desde += timedelta(days=PERIODO_DIAS)
    return periodos


def _evaluar_periodo(
    db: Session, modelo: ModeloML, desde: date, hasta: date, umbral: float
) -> PeriodoEvaluado | None:
    filas = forecast_repo.evaluables(db, modelo.id, desde, hasta)
    if not filas:
        return None

    por_producto: dict[uuid.UUID, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    reales: list[float] = []
    predichas: list[float] = []
    for producto_id, predicha, real in filas:
        reales.append(float(real))
        predichas.append(float(predicha))
        por_producto[producto_id][0].append(float(real))
        por_producto[producto_id][1].append(float(predicha))

    def _fila(producto_id: uuid.UUID | None, real: list[float], pred: list[float]) -> dict:
        m = contracts.calcular_metricas(real, pred)
        mape = None if m.mape is None else round(m.mape, 3)
        return {
            "modelo_id": modelo.id,
            "producto_id": producto_id,
            "tipo_evaluacion": TipoEvaluacion.PRODUCCION.value,
            "mae": round(m.mae, 4),
            "rmse": round(m.rmse, 4),
            "mape": mape,
            "n_muestras": m.n_muestras,
            "periodo_desde": desde,
            "periodo_hasta": hasta,
            "supera_umbral": mape is not None and mape > umbral,
        }

    global_ = _fila(None, reales, predichas)
    model_repo.reemplazar_metricas_periodo(
        db,
        modelo.id,
        TipoEvaluacion.PRODUCCION.value,
        desde,
        hasta,
        [global_, *(_fila(pid, r, p) for pid, (r, p) in por_producto.items())],
    )
    return PeriodoEvaluado(
        desde=desde,
        hasta=hasta,
        mape=global_["mape"],
        mae=global_["mae"],
        rmse=global_["rmse"],
        n_muestras=global_["n_muestras"],
        supera_umbral=global_["supera_umbral"],
    )


def _consecutivos_sobre_umbral(db: Session, modelo_id: uuid.UUID) -> int:
    """Periodos más recientes seguidos con `supera_umbral` (se corta en el primero que no)."""
    recientes = model_repo.ultimas_globales(
        db, modelo_id, TipoEvaluacion.PRODUCCION.value, limite=_MAX_PERIODOS_POR_EJECUCION
    )
    consecutivos = 0
    for metrica in recientes:
        if not metrica.supera_umbral:
            break
        consecutivos += 1
    return consecutivos


def _alertar_degradacion(
    db: Session, modelo: ModeloML, config: MlConfig, resultado: ResultadoEvaluacion
) -> uuid.UUID:
    existente = alert_repo.abierta_de_modelo(db, tipo=TipoAlerta.MAPE_UMBRAL, modelo_id=modelo.id)
    if existente is not None:
        return existente.id
    ultimo = resultado.periodos[-1]
    mape = "s/d" if ultimo.mape is None else f"{ultimo.mape:.1f} %"
    alerta = alert_repo.crear(
        db,
        tipo=TipoAlerta.MAPE_UMBRAL,
        severidad=Severidad.CRITICA,
        modelo_id=modelo.id,
        mensaje=(
            f"El MAPE de producción ({mape}) supera el umbral de {config.umbral_mape:.1f} % "
            f"durante {resultado.periodos_consecutivos} periodos consecutivos "
            f"(modelo {modelo.algoritmo} {modelo.version}). Se encoló un reentrenamiento."
        ),
    )
    return alerta.id


def _encolar_reentrenamiento(db: Session, modelo: ModeloML) -> uuid.UUID:
    """Un solo reentrenamiento activo a la vez: reutiliza el que ya está en cola/ejecución."""
    activo = job_repo.activo_de_tipo(db, TipoJob.REENTRENAMIENTO)
    if activo is not None:
        return activo.id
    job = job_repo.crear(
        db,
        tipo=TipoJob.REENTRENAMIENTO,
        parametros={
            "algoritmos": [modelo.algoritmo],
            "motivo": MotivoEntrenamiento.DEGRADACION.value,
            "promover_automaticamente": True,
            "modelo_origen_id": str(modelo.id),
        },
    )
    return job.id


# ------------------------------------------------------------------ consulta (GET /ml/metrics)
def estado_degradacion(db: Session, modelo: ModeloML) -> Degradacion:
    config = obtener_config(db)
    actuales = _consecutivos_sobre_umbral(db, modelo.id)
    job = job_repo.ultimo_reentrenamiento_completado(db)
    resultado = None
    if job is not None and job.resultado_modelo_id is not None:
        candidato = model_repo.obtener(db, job.resultado_modelo_id)
        resultado = None if candidato is None else candidato.estado
    return Degradacion(
        umbral_mape=config.umbral_mape,
        periodos_consecutivos_requeridos=config.periodos_consecutivos,
        periodos_consecutivos_actuales=actuales,
        requiere_reentrenamiento=actuales >= config.periodos_consecutivos,
        ultimo_reentrenamiento=None if job is None else job.finalizado_en,
        ultimo_reentrenamiento_resultado=resultado,
    )


def consultar_metricas(
    db: Session,
    *,
    modelo_id: uuid.UUID | None,
    tipo: TipoEvaluacion,
    desde: date,
    hasta: date,
    producto_id: uuid.UUID | None,
) -> MetricsResponse:
    if desde > hasta:
        raise AppError(
            "RANGO_FECHAS_INVALIDO",
            "El campo `desde` no puede ser posterior a `hasta`.",
            status_code=422,
            detalle={"campo": "desde"},
        )
    modelo = _resolver_modelo(db, modelo_id)
    serie = model_repo.metricas(
        db,
        modelo.id,
        tipo.value,
        desde=desde,
        hasta=hasta,
        producto_id=producto_id,
        solo_globales=producto_id is None,
    )
    ultimo = serie[-1] if serie else None
    peores = (
        []
        if producto_id is not None
        else _peores_productos(
            db,
            model_repo.metricas(
                db, modelo.id, tipo.value, desde=desde, hasta=hasta, solo_productos=True
            ),
        )
    )
    return MetricsResponse(
        modelo_id=modelo.id,
        modelo=ModeloInfo(
            id=modelo.id,
            nombre=modelo.nombre,
            algoritmo=modelo.algoritmo,
            version=modelo.version,
            estado=modelo.estado,
        ),
        resumen=ResumenMetricas(
            mae=None if ultimo is None else float(ultimo.mae),
            rmse=None if ultimo is None else float(ultimo.rmse),
            mape=None if ultimo is None or ultimo.mape is None else float(ultimo.mape),
        ),
        serie=[_punto(m) for m in serie],
        peores_productos=peores,
        degradacion=estado_degradacion(db, modelo),
    )


def listar_modelos(db: Session) -> list[ModeloResumen]:
    """Historial de la familia de modelos (más reciente primero) con su MAPE de holdout."""
    resumen = []
    for m in model_repo.listar_de_familia(db, get_settings().ml_modelo_nombre):
        holdout = model_repo.ultimas_globales(db, m.id, TipoEvaluacion.HOLDOUT.value, limite=1)
        mape = holdout[0].mape if holdout else None
        resumen.append(
            ModeloResumen(
                id=m.id,
                version=m.version,
                algoritmo=m.algoritmo,
                estado=m.estado,
                motivo_entrenamiento=m.motivo_entrenamiento,
                entrenado_en=m.entrenado_en,
                promovido_en=m.promovido_en,
                mape_holdout=None if mape is None else float(mape),
            )
        )
    return resumen


def _resolver_modelo(db: Session, modelo_id: uuid.UUID | None) -> ModeloML:
    if modelo_id is not None:
        modelo = model_repo.obtener(db, modelo_id)
        if modelo is None:
            raise AppError("MODELO_NO_ENCONTRADO", "El modelo indicado no existe.", status_code=404)
        return modelo
    modelo = model_repo.obtener_produccion(db, get_settings().ml_modelo_nombre)
    if modelo is None:
        raise AppError(
            "SIN_MODELO_PRODUCTIVO",
            "No hay un modelo en estado `produccion`; entrene y promueva uno primero.",
        )
    return modelo


def _punto(m: MetricaEvaluacion) -> MetricPoint:
    return MetricPoint(
        periodo_desde=m.periodo_desde,
        periodo_hasta=m.periodo_hasta,
        mae=float(m.mae),
        rmse=float(m.rmse),
        mape=None if m.mape is None else float(m.mape),
        n_muestras=m.n_muestras,
        supera_umbral=m.supera_umbral,
    )


def _peores_productos(db: Session, filas: Sequence[MetricaEvaluacion]) -> list[PeorProducto]:
    """Top de productos por MAPE del último periodo en rango; tendencia vs. el anterior."""
    historial: dict[uuid.UUID, list[MetricaEvaluacion]] = defaultdict(list)
    for fila in filas:  # ya vienen ordenadas por periodo ascendente
        historial[fila.producto_id].append(fila)

    ordenados = sorted(
        historial.items(),
        key=lambda kv: (
            kv[1][-1].mape is None,
            -float(kv[1][-1].mape or 0),
            -float(kv[1][-1].mae),
        ),
    )[:_TOP_PEORES_PRODUCTOS]
    catalogo = catalog_repo.productos_resumen(db, [pid for pid, _ in ordenados])
    peores = []
    for pid, serie in ordenados:
        actual = serie[-1]
        sku, nombre = catalogo.get(pid, (None, None))
        peores.append(
            PeorProducto(
                producto_id=pid,
                sku=sku,
                nombre=nombre,
                mae=float(actual.mae),
                rmse=float(actual.rmse),
                mape=None if actual.mape is None else float(actual.mape),
                tendencia=_tendencia(serie),
            )
        )
    return peores


def _tendencia(serie: Sequence[MetricaEvaluacion]) -> Literal["sube", "baja", "estable"] | None:
    if len(serie) < 2 or serie[-1].mape is None or serie[-2].mape is None:
        return None
    delta = float(serie[-1].mape) - float(serie[-2].mape)
    if delta > _TOLERANCIA_TENDENCIA:
        return "sube"
    if delta < -_TOLERANCIA_TENDENCIA:
        return "baja"
    return "estable"
