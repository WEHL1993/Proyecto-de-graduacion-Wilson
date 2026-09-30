"""Gobernanza ML contra PostgreSQL real (Fase 6): TC-ML-01..04, TC-MET-01/02 y TC-RBAC-01.

Requiere la BD migrada; se omiten si no hay conexión. Cada prueba corre en una transacción que se
revierte al final; los artefactos se escriben en un directorio temporal.
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.security import create_access_token, hash_password
from app.domain.enums import (
    EstadoAlerta,
    EstadoJob,
    EstadoModelo,
    Severidad,
    TipoAlerta,
    TipoEvaluacion,
    TipoJob,
)
from app.domain.models.auth import Permiso, Rol, Usuario
from app.domain.models.catalog import Categoria, Producto, Ruta
from app.domain.models.ml import (
    Alerta,
    JobML,
    MetricaEvaluacion,
    ModeloML,
    PronosticoDemanda,
)
from app.domain.models.sales import EtlLote, VentaHistorica
from app.main import app
from app.ml.inference.cache import limpiar_cache
from app.repositories import parametro_repo
from app.schemas.ml import RetrainRequest
from app.services import (
    job_service,
    monitoring_service,
    prediction_service,
    retraining_service,
    training_service,
)
from app.workers.jobs import evaluate_production, retrain_model
from tests.ml.conftest import FECHA_FIN, generar_ventas

NOMBRE = "demanda_gobernanza"
INICIO = date(2026, 3, 2)  # lunes: los periodos de 7 días arrancan aquí


@pytest.fixture
def db_session():
    try:
        connection = get_engine().connect()
    except (OperationalError, UnicodeDecodeError):  # psycopg2 en Windows
        pytest.skip("PostgreSQL no disponible")
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def entorno(db_session, tmp_path, monkeypatch):
    settings = SimpleNamespace(ml_artifacts_dir=tmp_path, ml_modelo_nombre=NOMBRE)
    for modulo in (monitoring_service, retraining_service, training_service, prediction_service):
        monkeypatch.setattr(modulo, "get_settings", lambda: settings)
    limpiar_cache()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield SimpleNamespace(db=db_session, client=TestClient(app))
    finally:
        app.dependency_overrides.clear()
        limpiar_cache()


# ------------------------------------------------------------------ helpers
def _usuario(db: Session, permisos: list[str]) -> tuple[dict[str, str], Usuario]:
    rol = Rol(nombre=f"rol-{uuid.uuid4().hex[:8]}", descripcion="prueba")
    for codigo in permisos:
        permiso = db.scalar(select(Permiso).where(Permiso.codigo == codigo))
        rol.permisos.append(permiso or Permiso(codigo=codigo, descripcion=codigo))
    usuario = Usuario(
        email=f"ml-{uuid.uuid4().hex[:8]}@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo="Prueba ML",
        roles=[rol],
    )
    db.add(usuario)
    db.flush()
    token, _ = create_access_token(sub=str(usuario.id), roles=[rol.nombre], perms=permisos)
    return {"Authorization": f"Bearer {token}"}, usuario


def _catalogo(db: Session) -> SimpleNamespace:
    categoria = Categoria(nombre=f"cat-{uuid.uuid4().hex[:6]}")
    db.add(categoria)
    db.flush()
    producto = Producto(
        sku=f"G{uuid.uuid4().hex[:8]}", nombre="Gaseosa 2L", categoria_id=categoria.id
    )
    ruta = Ruta(codigo=f"R{uuid.uuid4().hex[:6]}", nombre="Ruta prueba")
    db.add_all([producto, ruta])
    db.flush()
    return SimpleNamespace(producto=producto, ruta=ruta)


def _modelo(
    db: Session,
    estado: EstadoModelo,
    *,
    algoritmo: str = "xgboost",
    mape_holdout: float | None = None,
) -> ModeloML:
    modelo = ModeloML(
        nombre=NOMBRE,
        algoritmo=algoritmo,
        version=f"v9.{uuid.uuid4().hex[:6]}",
        estado=estado,
        ruta_artefacto="models/x",
        hash_artefacto="a" * 64,
        hiperparametros={},
        esquema_features={},
        ventana_desde=date(2025, 1, 1),
        ventana_hasta=date(2025, 12, 31),
        motivo_entrenamiento="manual",
        promovido_en=None,
    )
    if estado == EstadoModelo.PRODUCCION:
        modelo.promovido_en = INICIO
    db.add(modelo)
    db.flush()
    if mape_holdout is not None:
        _metrica(db, modelo, TipoEvaluacion.HOLDOUT, mape_holdout, INICIO, INICIO + timedelta(13))
    return modelo


def _metrica(
    db: Session,
    modelo: ModeloML,
    tipo: TipoEvaluacion,
    mape: float,
    desde: date,
    hasta: date,
    *,
    producto_id: uuid.UUID | None = None,
    umbral: float = 12.0,
) -> MetricaEvaluacion:
    fila = MetricaEvaluacion(
        modelo_id=modelo.id,
        producto_id=producto_id,
        tipo_evaluacion=tipo.value,
        mae=Decimal("10.0"),
        rmse=Decimal("14.0"),
        mape=Decimal(str(mape)),
        n_muestras=7,
        periodo_desde=desde,
        periodo_hasta=hasta,
        supera_umbral=mape > umbral,
    )
    db.add(fila)
    db.flush()
    return fila


def _periodo(n: int) -> tuple[date, date]:
    """Periodo n-ésimo (0 = primero) de 7 días desde INICIO."""
    desde = INICIO + timedelta(days=7 * n)
    return desde, desde + timedelta(days=6)


def _pronosticos_con_ventas(
    db: Session,
    modelo: ModeloML,
    cat: SimpleNamespace,
    usuario: Usuario,
    n_periodo: int,
    *,
    real: float = 100.0,
    predicha: float = 86.6,
    dias: int = 7,
) -> None:
    """Pronósticos h=1 de `dias` días del periodo y sus ventas reales (MAPE = |r-p|/r)."""
    desde, _ = _periodo(n_periodo)
    lote = EtlLote(
        usuario_id=usuario.id, archivo_nombre="m.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    db.add(lote)
    db.flush()
    for i in range(dias):
        fecha = desde + timedelta(days=i)
        db.add(
            VentaHistorica(
                lote_id=lote.id,
                fecha_venta=fecha,
                producto_id=cat.producto.id,
                ruta_id=cat.ruta.id,
                cantidad=Decimal(str(real)),
                precio_unitario=Decimal("10.00"),
                monto_total=Decimal(str(real)) * 10,
            )
        )
        db.add(
            PronosticoDemanda(
                modelo_id=modelo.id,
                producto_id=cat.producto.id,
                ruta_id=cat.ruta.id,
                fecha_objetivo=fecha,
                horizonte_dias=1,
                demanda_predicha=Decimal(str(predicha)),
            )
        )
    db.flush()


def _parametros(db: Session, umbral: float = 12.0, periodos: int = 3) -> None:
    parametro_repo.guardar_valor(db, "ml.mape_umbral", umbral)
    parametro_repo.guardar_valor(db, "ml.periodos_consecutivos", periodos)


def _jobs_reentrenamiento(db: Session) -> list[JobML]:
    return list(db.scalars(select(JobML).where(JobML.tipo == TipoJob.REENTRENAMIENTO)))


def _alertas_mape(db: Session, modelo: ModeloML) -> list[Alerta]:
    return list(
        db.scalars(
            select(Alerta).where(
                Alerta.tipo == TipoAlerta.MAPE_UMBRAL, Alerta.modelo_id == modelo.id
            )
        )
    )


# ------------------------------------------------------------------ TC-ML-01
def test_tc_ml_01_tercer_periodo_sobre_umbral_dispara_alerta_y_reentrenamiento(entorno):
    db = entorno.db
    _, usuario = _usuario(db, [])
    cat = _catalogo(db)
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 12.8, *_periodo(0))
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 13.1, *_periodo(1))
    _pronosticos_con_ventas(db, modelo, cat, usuario, 2)  # MAPE = 13.4 %

    resultado = evaluate_production.ejecutar(db)

    assert resultado.estado == "evaluado" and resultado.degradacion_detectada
    assert resultado.periodos_consecutivos == 3
    global_ = db.scalars(
        select(MetricaEvaluacion).where(
            MetricaEvaluacion.modelo_id == modelo.id,
            MetricaEvaluacion.periodo_desde == _periodo(2)[0],
            MetricaEvaluacion.producto_id.is_(None),
        )
    ).one()
    assert float(global_.mape) == pytest.approx(13.4) and global_.supera_umbral is True
    assert global_.tipo_evaluacion == "produccion" and global_.n_muestras == 7

    alerta = _alertas_mape(db, modelo)
    assert len(alerta) == 1 and alerta[0].severidad == Severidad.CRITICA
    assert alerta[0].estado == EstadoAlerta.ABIERTA

    jobs = _jobs_reentrenamiento(db)
    assert len(jobs) == 1 and jobs[0].estado == EstadoJob.EN_COLA
    assert jobs[0].parametros["motivo"] == "degradacion"
    assert jobs[0].solicitado_por is None

    # Idempotencia: reejecutar no duplica métricas, alerta ni job.
    evaluate_production.ejecutar(db)
    assert len(_alertas_mape(db, modelo)) == 1 and len(_jobs_reentrenamiento(db)) == 1


def test_tc_ml_01_con_solo_dos_periodos_no_dispara(entorno):
    db = entorno.db
    _, usuario = _usuario(db, [])
    cat = _catalogo(db)
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 9.0, *_periodo(0))  # periodo sano
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 13.1, *_periodo(1))
    _pronosticos_con_ventas(db, modelo, cat, usuario, 2)  # 13.4 % -> solo 2 consecutivos

    resultado = evaluate_production.ejecutar(db)

    assert resultado.estado == "evaluado" and resultado.periodos_consecutivos == 2
    assert not resultado.degradacion_detectada
    assert _alertas_mape(db, modelo) == [] and _jobs_reentrenamiento(db) == []


def test_evaluacion_ignora_periodos_incompletos_y_sin_modelo(entorno):
    db = entorno.db
    assert evaluate_production.ejecutar(db).estado == "sin_modelo_productivo"

    _, usuario = _usuario(db, [])
    cat = _catalogo(db)
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    _pronosticos_con_ventas(db, modelo, cat, usuario, 0, dias=4)  # periodo sin completar

    assert evaluate_production.ejecutar(db).estado == "sin_datos"
    assert db.scalar(select(func.count()).select_from(MetricaEvaluacion)) == 0


def test_evaluacion_persiste_metricas_por_producto(entorno):
    db = entorno.db
    _, usuario = _usuario(db, [])
    cat = _catalogo(db)
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    _pronosticos_con_ventas(db, modelo, cat, usuario, 0)

    evaluate_production.ejecutar(db)

    por_producto = db.scalars(
        select(MetricaEvaluacion).where(
            MetricaEvaluacion.modelo_id == modelo.id,
            MetricaEvaluacion.producto_id == cat.producto.id,
        )
    ).one()
    assert float(por_producto.mape) == pytest.approx(13.4)
    # demanda_real quedó materializada en los pronósticos
    reales = db.scalars(select(PronosticoDemanda.demanda_real)).all()
    assert reales and all(r == Decimal("100.00") for r in reales)


# ------------------------------------------------------------------ TC-ML-02 / TC-ML-03
def _entrenador_falso(mape_por_algoritmo: dict[str, float]):
    def _entrenar(
        db,
        *,
        algoritmo,
        motivo,
        entrenado_por,
        ventana_desde=None,
        ventana_hasta=None,
        hiperparametros=None,
        promover=False,
    ):
        modelo = _modelo(
            db,
            EstadoModelo.CANDIDATO,
            algoritmo=algoritmo,
            mape_holdout=mape_por_algoritmo[algoritmo],
        )
        modelo.entrenado_por = entrenado_por
        return modelo

    return _entrenar


def _solicitar(db: Session, usuario: Usuario, **kwargs) -> JobML:
    solicitud = RetrainRequest(
        algoritmos=kwargs.pop("algoritmos", ["xgboost"]), motivo="degradacion", **kwargs
    )
    respuesta = retraining_service.solicitar(db, solicitud, usuario.id)
    assert respuesta.estado == "en_cola"
    return db.get(JobML, respuesta.job_id)


def test_tc_ml_02_candidato_mejor_se_promueve_y_archiva_al_anterior(entorno, monkeypatch):
    db = entorno.db
    _, usuario = _usuario(db, [])
    productivo = _modelo(db, EstadoModelo.PRODUCCION)
    _metrica(db, productivo, TipoEvaluacion.PRODUCCION, 13.4, *_periodo(2))
    alerta = Alerta(
        tipo=TipoAlerta.MAPE_UMBRAL,
        severidad=Severidad.CRITICA,
        modelo_id=productivo.id,
        mensaje="degradado",
    )
    db.add(alerta)
    db.flush()
    monkeypatch.setattr(
        training_service, "entrenar_modelo", _entrenador_falso({"xgboost": 9.0, "sklearn": 10.5})
    )
    job = _solicitar(db, usuario, algoritmos=["xgboost", "sklearn"])

    assert retrain_model.ejecutar(db) == job.id

    db.refresh(job)
    db.refresh(productivo)
    ganador = db.get(ModeloML, job.resultado_modelo_id)
    assert job.estado == EstadoJob.COMPLETADO
    assert ganador.estado == EstadoModelo.PRODUCCION and ganador.algoritmo == "xgboost"
    assert productivo.estado == EstadoModelo.ARCHIVADO
    perdedor = db.scalars(
        select(ModeloML).where(ModeloML.nombre == NOMBRE, ModeloML.algoritmo == "sklearn")
    ).one()
    assert perdedor.estado == EstadoModelo.DESCARTADO
    en_produccion = db.scalars(
        select(ModeloML).where(ModeloML.nombre == NOMBRE, ModeloML.estado == "produccion")
    ).all()
    assert [m.id for m in en_produccion] == [ganador.id]
    db.refresh(alerta)
    assert alerta.estado == EstadoAlerta.RESUELTA and alerta.resuelta_en is not None


def test_tc_ml_03_candidato_peor_se_descarta_y_produccion_queda_intacta(entorno, monkeypatch):
    db = entorno.db
    _, usuario = _usuario(db, [])
    productivo = _modelo(db, EstadoModelo.PRODUCCION)
    _metrica(db, productivo, TipoEvaluacion.PRODUCCION, 13.4, *_periodo(2))
    monkeypatch.setattr(training_service, "entrenar_modelo", _entrenador_falso({"xgboost": 15.0}))
    job = _solicitar(db, usuario)

    retrain_model.ejecutar(db)

    db.refresh(job)
    db.refresh(productivo)
    candidato = db.get(ModeloML, job.resultado_modelo_id)
    assert job.estado == EstadoJob.COMPLETADO
    assert candidato.estado == EstadoModelo.DESCARTADO
    assert productivo.estado == EstadoModelo.PRODUCCION
    info = _alertas_mape(db, candidato)
    assert len(info) == 1 and info[0].severidad == Severidad.INFO


def test_candidato_igual_no_se_promueve_y_sin_auto_promocion_queda_candidato(entorno, monkeypatch):
    db = entorno.db
    _, usuario = _usuario(db, [])
    productivo = _modelo(db, EstadoModelo.PRODUCCION)
    _metrica(db, productivo, TipoEvaluacion.PRODUCCION, 10.0, *_periodo(0))
    monkeypatch.setattr(training_service, "entrenar_modelo", _entrenador_falso({"xgboost": 10.0}))

    empate = _solicitar(db, usuario)
    retrain_model.ejecutar(db)
    db.refresh(empate)
    assert db.get(ModeloML, empate.resultado_modelo_id).estado == EstadoModelo.DESCARTADO

    monkeypatch.setattr(training_service, "entrenar_modelo", _entrenador_falso({"xgboost": 5.0}))
    manual = _solicitar(db, usuario, promover_automaticamente=False)
    retrain_model.ejecutar(db)
    db.refresh(manual)
    db.refresh(productivo)
    assert db.get(ModeloML, manual.resultado_modelo_id).estado == EstadoModelo.CANDIDATO
    assert productivo.estado == EstadoModelo.PRODUCCION


def test_reentrenamiento_sin_candidatos_falla_con_error_registrado(entorno):
    db = entorno.db
    _, usuario = _usuario(db, [])
    _catalogo(db)
    job = _solicitar(db, usuario, algoritmos=["lstm"])  # sin datos ni soporte -> falla

    retrain_model.ejecutar(db)

    db.refresh(job)
    assert job.estado == EstadoJob.FALLIDO and job.error
    assert job.finalizado_en is not None


def test_solo_un_reentrenamiento_activo(entorno):
    db = entorno.db
    headers, usuario = _usuario(db, ["ml:reentrenar"])
    cuerpo = {"algoritmos": ["xgboost"], "motivo": "manual"}
    primero = entorno.client.post("/api/v1/ml/models/retrain", json=cuerpo, headers=headers)
    segundo = entorno.client.post("/api/v1/ml/models/retrain", json=cuerpo, headers=headers)
    assert primero.status_code == 200
    assert segundo.status_code == 400 and segundo.json()["codigo"] == "REENTRENAMIENTO_EN_CURSO"
    assert segundo.json()["detalle"]["job_id"] == primero.json()["job_id"]


# ------------------------------------------------------------------ TC-ML-04 (extremo a extremo)
def test_tc_ml_04_reentrenamiento_manual_de_extremo_a_extremo(entorno):
    db = entorno.db
    headers, gerente = _usuario(db, ["ml:reentrenar", "ml:metricas:leer"])
    cat_ventas = generar_ventas()
    categoria = Categoria(nombre=f"cat-{uuid.uuid4().hex[:6]}")
    db.add(categoria)
    db.flush()
    lote = EtlLote(
        usuario_id=gerente.id, archivo_nombre="e2e.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    db.add(lote)
    productos = {
        p: Producto(sku=f"E{p[-6:]}", nombre="Prod", categoria_id=categoria.id)
        for p in cat_ventas["producto_id"].unique()
    }
    rutas = {r: Ruta(codigo=f"E{r[-6:]}", nombre="Ruta") for r in cat_ventas["ruta_id"].unique()}
    db.add_all([*productos.values(), *rutas.values()])
    db.flush()
    db.add_all(
        VentaHistorica(
            lote_id=lote.id,
            fecha_venta=v.fecha.date(),
            producto_id=productos[v.producto_id].id,
            ruta_id=rutas[v.ruta_id].id,
            cantidad=Decimal(str(v.cantidad)),
            precio_unitario=Decimal("10.00"),
            monto_total=Decimal(str(v.cantidad)) * 10,
        )
        for v in cat_ventas.itertuples()
    )
    db.flush()

    r = entorno.client.post(
        "/api/v1/ml/models/retrain",
        json={"algoritmos": ["sklearn"], "motivo": "manual"},
        headers=headers,
    )
    assert r.status_code == 200 and r.json()["estado"] == "en_cola"
    job_id = r.json()["job_id"]

    assert job_service.procesar_siguiente_reentrenamiento(db) == uuid.UUID(job_id)

    job = entorno.client.get(f"/api/v1/ml/jobs/{job_id}", headers=headers).json()
    assert job["estado"] == "completado" and job["resultado_modelo_id"]
    modelo = db.get(ModeloML, uuid.UUID(job["resultado_modelo_id"]))
    assert modelo.entrenado_por == gerente.id and modelo.motivo_entrenamiento == "manual"
    assert modelo.estado == EstadoModelo.PRODUCCION  # sin productivo previo: se promueve

    metricas = entorno.client.get(
        "/api/v1/ml/metrics",
        params={
            "modelo_id": str(modelo.id),
            "tipo_evaluacion": "holdout",
            "desde": "2025-01-01",
            "hasta": FECHA_FIN.date().isoformat(),
        },
        headers=headers,
    )
    assert metricas.status_code == 200, metricas.text
    assert metricas.json()["serie"] and metricas.json()["modelo"]["estado"] == "produccion"

    modelos = entorno.client.get("/api/v1/ml/models", headers=headers).json()["modelos"]
    assert [m["id"] for m in modelos] == [str(modelo.id)]


# ------------------------------------------------------------------ TC-MET-01 / TC-MET-02
URL_METRICAS = "/api/v1/ml/metrics"


def test_tc_met_01_metricas_resumen_serie_peores_y_degradacion(entorno):
    db = entorno.db
    headers, _ = _usuario(db, ["ml:metricas:leer"])
    cat = _catalogo(db)
    otro = Producto(
        sku=f"O{uuid.uuid4().hex[:8]}", nombre="Agua 600ml", categoria_id=cat.producto.categoria_id
    )
    db.add(otro)
    db.flush()
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    for n, mape in enumerate([12.8, 13.1]):
        _metrica(db, modelo, TipoEvaluacion.PRODUCCION, mape, *_periodo(n))
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 8.0, *_periodo(2))  # rompe la racha
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 19.8, *_periodo(3), producto_id=cat.producto.id)
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 15.0, *_periodo(2), producto_id=cat.producto.id)
    _metrica(db, modelo, TipoEvaluacion.PRODUCCION, 7.5, *_periodo(3), producto_id=otro.id)

    r = entorno.client.get(
        URL_METRICAS,
        params={"desde": INICIO.isoformat(), "hasta": (INICIO + timedelta(60)).isoformat()},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["modelo_id"] == str(modelo.id)
    assert [p["mape"] for p in cuerpo["serie"]] == [12.8, 13.1, 8.0]
    assert cuerpo["resumen"] == {"mae": 10.0, "rmse": 14.0, "mape": 8.0}
    peores = cuerpo["peores_productos"]
    assert [p["nombre"] for p in peores] == ["Gaseosa 2L", "Agua 600ml"]
    assert peores[0]["tendencia"] == "sube" and peores[1]["tendencia"] is None
    deg = cuerpo["degradacion"]
    assert deg["umbral_mape"] == 12.0 and deg["periodos_consecutivos_requeridos"] == 3
    assert deg["periodos_consecutivos_actuales"] == 0 and deg["requiere_reentrenamiento"] is False


def test_metricas_requiere_reentrenamiento_coherente_con_umbral(entorno):
    db = entorno.db
    headers, _ = _usuario(db, ["ml:metricas:leer"])
    _parametros(db)
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    for n, mape in enumerate([12.8, 13.1, 13.4]):
        _metrica(db, modelo, TipoEvaluacion.PRODUCCION, mape, *_periodo(n))

    deg = entorno.client.get(
        URL_METRICAS, params={"desde": "2026-01-01", "hasta": "2026-12-31"}, headers=headers
    ).json()["degradacion"]

    assert deg["periodos_consecutivos_actuales"] == 3 and deg["requiere_reentrenamiento"] is True


def test_tc_met_02_rango_invalido_devuelve_422_con_campo(entorno):
    headers, _ = _usuario(entorno.db, ["ml:metricas:leer"])
    _modelo(entorno.db, EstadoModelo.PRODUCCION)
    r = entorno.client.get(
        URL_METRICAS, params={"desde": "2026-06-01", "hasta": "2026-01-01"}, headers=headers
    )
    assert r.status_code == 422 and r.json()["detalle"]["campo"] == "desde"
    faltante = entorno.client.get(URL_METRICAS, params={"desde": "2026-06-01"}, headers=headers)
    assert faltante.status_code == 422


def test_metricas_sin_modelo_productivo_y_sin_token(entorno):
    headers, _ = _usuario(entorno.db, ["ml:metricas:leer"])
    params = {"desde": "2026-01-01", "hasta": "2026-12-31"}
    r = entorno.client.get(URL_METRICAS, params=params, headers=headers)
    assert r.status_code == 400 and r.json()["codigo"] == "SIN_MODELO_PRODUCTIVO"
    assert entorno.client.get(URL_METRICAS, params=params).status_code == 401


# ------------------------------------------------------------------ TC-RBAC-01
def test_tc_rbac_01_bodega_no_puede_reentrenar(entorno, caplog):
    db = entorno.db
    headers, bodega = _usuario(db, ["carga_ruta:despachar", "inventario:leer", "alertas:leer"])

    with caplog.at_level(logging.WARNING, logger="app.auditoria"):
        r = entorno.client.post(
            "/api/v1/ml/models/retrain",
            json={"algoritmos": ["xgboost"], "motivo": "manual"},
            headers=headers,
        )

    assert r.status_code == 403 and r.json()["codigo"] == "PERMISO_DENEGADO"
    assert _jobs_reentrenamiento(db) == []  # ningún job creado
    registro = next(rec for rec in caplog.records if rec.name == "app.auditoria")
    assert "PERMISO_DENEGADO" in registro.message and str(bodega.id) in registro.message
    assert "ml:reentrenar" in registro.message


def test_rbac_matriz_de_endpoints_ml(entorno):
    db = entorno.db
    sin_permisos, _ = _usuario(db, ["alertas:leer"])
    solo_lectura, _ = _usuario(db, ["ml:metricas:leer"])
    cliente = entorno.client
    params = {"desde": "2026-01-01", "hasta": "2026-12-31"}

    assert cliente.get(URL_METRICAS, params=params, headers=sin_permisos).status_code == 403
    assert cliente.get("/api/v1/ml/models", headers=sin_permisos).status_code == 403
    assert cliente.get(f"/api/v1/ml/jobs/{uuid.uuid4()}", headers=sin_permisos).status_code == 403
    cuerpo = {"umbral_mape": 10, "periodos_consecutivos": 2}
    assert cliente.put("/api/v1/ml/config", json=cuerpo, headers=solo_lectura).status_code == 403
    reentrenar = {"algoritmos": ["xgboost"], "motivo": "manual"}
    assert (
        cliente.post("/api/v1/ml/models/retrain", json=reentrenar, headers=solo_lectura).status_code
        == 403
    )
    assert cliente.get(f"/api/v1/ml/jobs/{uuid.uuid4()}", headers=solo_lectura).status_code == 404
    assert cliente.get("/api/v1/ml/models").status_code == 401


def test_validacion_del_cuerpo_de_reentrenamiento(entorno):
    headers, _ = _usuario(entorno.db, ["ml:reentrenar"])
    url = "/api/v1/ml/models/retrain"
    for cuerpo in (
        {"algoritmos": [], "motivo": "manual"},
        {"algoritmos": ["xgboost"], "motivo": "otro"},
        {"algoritmos": ["xgboost", "xgboost"], "motivo": "manual"},
        {
            "algoritmos": ["xgboost"],
            "motivo": "manual",
            "ventana_desde": "2026-02-01",
            "ventana_hasta": "2026-01-01",
        },
    ):
        assert entorno.client.post(url, json=cuerpo, headers=headers).status_code == 422
    assert _jobs_reentrenamiento(entorno.db) == []


# ------------------------------------------------------------------ configuración y alertas
def test_config_de_degradacion_se_guarda_y_afecta_la_evaluacion(entorno):
    db = entorno.db
    lector, _ = _usuario(db, ["ml:metricas:leer"])
    gerente, _ = _usuario(db, ["ml:reentrenar"])
    r = entorno.client.put(
        "/api/v1/ml/config", json={"umbral_mape": 8.5, "periodos_consecutivos": 2}, headers=gerente
    )
    assert r.status_code == 200
    leido = entorno.client.get("/api/v1/ml/config", headers=lector).json()
    assert leido == {"umbral_mape": 8.5, "periodos_consecutivos": 2}
    invalido = entorno.client.put(
        "/api/v1/ml/config", json={"umbral_mape": 0, "periodos_consecutivos": 0}, headers=gerente
    )
    assert invalido.status_code == 422


def test_bandeja_de_alertas_ordena_criticas_primero(entorno):
    db = entorno.db
    # `mape_umbral` solo se muestra a quien tiene permisos de ML (visibilidad por rol, fase 8).
    headers, _ = _usuario(db, ["alertas:leer", "ml:metricas:leer"])
    modelo = _modelo(db, EstadoModelo.PRODUCCION)
    for severidad in (Severidad.INFO, Severidad.CRITICA, Severidad.ADVERTENCIA):
        db.add(
            Alerta(
                tipo=TipoAlerta.MAPE_UMBRAL,
                severidad=severidad,
                modelo_id=modelo.id,
                mensaje=severidad.value,
            )
        )
    db.flush()
    r = entorno.client.get("/api/v1/alerts", params={"limit": 100}, headers=headers)
    assert r.status_code == 200
    mensajes = [a["mensaje"] for a in r.json()["alertas"] if a["modelo_id"] == str(modelo.id)]
    assert mensajes == ["critica", "advertencia", "info"]
    assert r.json()["total"] >= 3


def test_catalogo_de_rutas_para_cualquier_usuario_autenticado(entorno):
    headers, _ = _usuario(entorno.db, [])
    cat = _catalogo(entorno.db)
    r = entorno.client.get("/api/v1/catalog/routes", headers=headers)
    assert r.status_code == 200
    assert str(cat.ruta.id) in {ruta["id"] for ruta in r.json()}
    assert entorno.client.get("/api/v1/catalog/routes").status_code == 401
