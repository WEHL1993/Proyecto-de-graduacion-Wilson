"""E2E del backend (ADR-14): Excel inicial → entrenamiento inicial → liquidaciones diarias →
demanda_real → evaluate_production → MAPE en Monitoreo → degradación → reentrenamiento con
liquidaciones. Usa el pipeline ML real (modelo pequeño) contra PostgreSQL."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.domain.enums import EstadoAlerta, EstadoJob, OrigenDatos, TipoAlerta, TipoJob
from app.domain.models.catalog import Categoria, Producto, Ruta
from app.domain.models.ml import Alerta, JobML, ModeloML, PronosticoDemanda
from app.domain.models.sales import EtlLote, VentaHistorica
from app.repositories import parametro_repo
from app.schemas.liquidacion import LiquidacionRequest
from app.services import (
    job_service,
    liquidacion_service,
    monitoring_service,
    prediction_service,
    retraining_service,
    training_service,
)
from app.workers.jobs import evaluate_production, retrain_model

from .conftest import crear_usuario, encabezados

NOMBRE = "demanda_e2e"
BASE_INICIO = date(2025, 10, 1)
BASE_DIAS = 120
LIQ_INICIO = date(2026, 3, 1)  # hueco de un mes sin información entre la base y lo liquidado
LIQ_DIAS = 50  # >= 28 de historia + 14 del holdout en el último tramo
HP = {"n_estimators": 40, "max_depth": 3, "n_jobs": 1}


@pytest.fixture
def e(db_tx, cliente, tmp_path, monkeypatch):
    settings = SimpleNamespace(ml_artifacts_dir=tmp_path, ml_modelo_nombre=NOMBRE)
    for modulo in (monitoring_service, retraining_service, training_service, prediction_service):
        monkeypatch.setattr(modulo, "get_settings", lambda: settings)
    db = db_tx
    admin = crear_usuario(db, "admin-e2e")
    vendedor = crear_usuario(db, "vendedor-e2e")
    categoria = Categoria(nombre=f"cat-{uuid.uuid4().hex[:6]}")
    db.add(categoria)
    db.flush()
    producto = Producto(
        sku=f"E{uuid.uuid4().hex[:8]}",
        nombre="Gaseosa",
        categoria_id=categoria.id,
        precio_venta=Decimal("50"),
    )
    ruta = Ruta(codigo=f"R{uuid.uuid4().hex[:6]}", nombre="Ruta E2E", vendedor_id=vendedor.id)
    db.add_all([producto, ruta])
    db.flush()
    return SimpleNamespace(
        db=db, c=cliente, admin=admin, vendedor=vendedor, producto=producto, ruta=ruta
    )


def _base_excel(e) -> None:
    """Histórico inicial (lote Excel): ~40 unidades con repunte de fin de semana."""
    lote = EtlLote(
        usuario_id=e.admin.id, archivo_nombre="base.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    e.db.add(lote)
    e.db.flush()
    for i in range(BASE_DIAS):
        dia = BASE_INICIO + timedelta(days=i)
        cantidad = Decimal(40 + 10 * (dia.weekday() >= 4) + i % 3)
        e.db.add(
            VentaHistorica(
                lote_id=lote.id,
                fecha_venta=dia,
                producto_id=e.producto.id,
                ruta_id=e.ruta.id,
                vendedor_id=e.vendedor.id,
                cantidad=cantidad,
                precio_unitario=Decimal(50),
                monto_total=cantidad * 50,
            )
        )
    e.db.flush()


def _liquidar(e, dia: date, vendidas: int, agotado: bool = False) -> None:
    venta = Decimal(vendidas) * 50
    solicitud = LiquidacionRequest.model_validate(
        {
            "fecha": dia,
            "ruta_id": e.ruta.id,
            "lineas": [
                {
                    "producto_id": e.producto.id,
                    "cantidad_cargada": vendidas,
                    "cantidad_vendida": vendidas,
                    "agotado": agotado,
                }
            ],
            "pagos": {"efectivo": venta, "efectivo_entregado": venta},
        }
    )
    borrador = liquidacion_service.guardar_borrador(e.db, solicitud, e.admin.id)
    liquidacion_service.cerrar(e.db, borrador.id, e.admin.id)


def test_flujo_completo_excel_liquidacion_degradacion_y_reentrenamiento(e):
    """TC-LIQ-15: Excel inicial → liquidar → evaluar → degradación → reentrenar."""
    db = e.db
    _base_excel(e)

    # 1) Entrenamiento inicial: solo Excel, calendario clásico (sin cobertura).
    inicial = training_service.entrenar_modelo(
        db, algoritmo="xgboost", hiperparametros=HP, promover=True
    )
    assert inicial.fuentes_datos["fuente"] == "excel_historico"
    assert set(inicial.fuentes_datos["origenes"]) == {"excel_historico"}
    assert inicial.fuentes_datos["origenes"]["excel_historico"]["filas"] == BASE_DIAS

    # 2) Pronósticos persistidos de las dos primeras semanas (planes de carga) y el umbral.
    for i in range(14):
        db.add(
            PronosticoDemanda(
                modelo_id=inicial.id,
                producto_id=e.producto.id,
                ruta_id=e.ruta.id,
                fecha_objetivo=LIQ_INICIO + timedelta(days=i),
                horizonte_dias=1,
                demanda_predicha=Decimal(40),
            )
        )
    parametro_repo.guardar_valor(db, "ml.periodos_consecutivos", 2)
    db.flush()

    # 3) Liquidaciones diarias: la demanda real triplica lo pronosticado (el modelo degrada).
    for i in range(LIQ_DIAS):
        _liquidar(e, LIQ_INICIO + timedelta(days=i), vendidas=120, agotado=(i == 30))

    reales = db.scalars(
        select(PronosticoDemanda.demanda_real).where(PronosticoDemanda.modelo_id == inicial.id)
    ).all()
    assert len(reales) == 14 and all(r == 120 for r in reales)
    origenes = set(db.scalars(select(EtlLote.origen)))
    assert origenes == {OrigenDatos.EXCEL_HISTORICO, OrigenDatos.LIQUIDACION} | {
        OrigenDatos.LIQUIDACION
    }
    # TC-LIQ-04: N cierres → un solo job en cola; lo completa el Worker, no la petición.
    en_cola = db.scalars(
        select(JobML).where(JobML.tipo == TipoJob.EVALUACION_PRODUCCION, JobML.estado == "en_cola")
    ).all()
    assert len(en_cola) == 1  # coalescidas: 50 cierres, un solo job

    # 4) El Worker evalúa: MAPE de producción y degradación tras 2 periodos consecutivos.
    evaluate_production.ejecutar_en_cola(db)
    assert job_service.procesar_evaluacion_en_cola(db) is None
    metricas = e.c.get(
        "/api/v1/ml/metrics",
        params={"desde": "2026-03-01", "hasta": "2026-04-30"},
        headers=encabezados(e.admin, "ml:metricas:leer"),
    )
    assert metricas.status_code == 200, metricas.text
    cuerpo = metricas.json()
    assert cuerpo["resumen"]["mape"] == pytest.approx(66.7, abs=0.5)
    assert cuerpo["degradacion"]["requiere_reentrenamiento"] is True
    alerta = db.scalars(select(Alerta).where(Alerta.tipo == TipoAlerta.MAPE_UMBRAL)).one()
    assert alerta.estado == EstadoAlerta.ABIERTA
    job = db.scalars(select(JobML).where(JobML.tipo == TipoJob.REENTRENAMIENTO)).one()
    assert job.parametros["motivo"] == "degradacion"

    # 5) Reentrenamiento por degradación: base Excel + liquidaciones, con trazabilidad.
    assert retrain_model.ejecutar_pendientes(db) == [job.id]
    db.refresh(job)
    assert job.estado == EstadoJob.COMPLETADO, job.error
    candidato = db.get(ModeloML, job.resultado_modelo_id)
    fuentes = candidato.fuentes_datos
    assert fuentes["fuente"] == "excel_mas_liquidacion"
    assert set(fuentes["origenes"]) == {"excel_historico", "liquidacion"}
    assert fuentes["origenes"]["liquidacion"]["filas"] == LIQ_DIAS
    assert fuentes["dias_liquidados"] == LIQ_DIAS
    assert fuentes["observaciones_censuradas"] == 1  # el día `agotado`
    assert candidato.ventana_desde == BASE_INICIO and candidato.ventana_hasta >= LIQ_INICIO


def test_reentrenar_solo_con_liquidaciones_exige_28_dias_por_ruta(e):
    """TC-LIQ-14: tramo corto → 400 HISTORIAL_INSUFICIENTE."""
    _base_excel(e)
    for i in range(10):
        _liquidar(e, LIQ_INICIO + timedelta(days=i), vendidas=40)
    from app.core.errors import AppError
    from app.domain.enums import FuenteReentrenamiento

    with pytest.raises(AppError) as exc:
        training_service.entrenar_modelo(
            e.db,
            algoritmo="xgboost",
            hiperparametros=HP,
            fuente=FuenteReentrenamiento.LIQUIDACION,
        )
    assert exc.value.codigo == "HISTORIAL_INSUFICIENTE"
    # Mixta con un último tramo corto: el holdout no cabe y también se reporta como tal.
    with pytest.raises(AppError) as exc:
        training_service.entrenar_modelo(
            e.db,
            algoritmo="xgboost",
            hiperparametros=HP,
            fuente=FuenteReentrenamiento.EXCEL_MAS_LIQUIDACION,
        )
    assert exc.value.codigo == "HISTORIAL_INSUFICIENTE"
