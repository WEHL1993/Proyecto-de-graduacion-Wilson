"""Liquidación diaria de ventas contra PostgreSQL real (ADR-14): TC-LIQ-01..16.

Requiere la BD migrada; se omiten si no hay conexión. Cada prueba corre en una transacción que
se revierte al final.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.domain.enums import (
    EstadoCarga,
    EstadoJob,
    EstadoLoteEtl,
    OrigenDatos,
    TipoAlerta,
    TipoJob,
)
from app.domain.models.catalog import Categoria, Producto, Ruta
from app.domain.models.ml import Alerta, JobML, ModeloML, PronosticoDemanda
from app.domain.models.operations import CargaRuta, DetalleCarga
from app.domain.models.sales import Comision, EtlLote, LiquidacionDiaria, VentaHistorica
from app.repositories import forecast_repo, parametro_repo
from app.services import job_service

from .conftest import crear_usuario, encabezados

URL = "/api/v1/liquidaciones"
FECHA = date(2026, 9, 1)
TODOS = (
    "liquidaciones:registrar",
    "liquidaciones:cerrar",
    "liquidaciones:corregir",
    "liquidaciones:leer",
)


@pytest.fixture
def e(db_tx, cliente):
    """Ruta con vendedor, dos productos (precio 50 y 30) y un administrador."""
    db = db_tx
    sufijo = uuid.uuid4().hex[:6]
    admin = crear_usuario(db, "admin-liq")
    vendedor = crear_usuario(db, "vendedor-liq")
    categoria = Categoria(nombre=f"cat-{sufijo}")
    db.add(categoria)
    db.flush()
    pa = Producto(
        sku=f"A-{sufijo}", nombre="Piña", categoria_id=categoria.id, precio_venta=Decimal("50")
    )
    pb = Producto(
        sku=f"B-{sufijo}", nombre="Cola", categoria_id=categoria.id, precio_venta=Decimal("30")
    )
    ruta = Ruta(codigo=f"R-{sufijo}", nombre="Cornelio", vendedor_id=vendedor.id)
    db.add_all([pa, pb, ruta])
    db.flush()
    db.commit()
    return SimpleNamespace(
        db=db,
        c=cliente,
        admin=admin,
        vendedor=vendedor,
        pa=pa,
        pb=pb,
        ruta=ruta,
        h=encabezados(admin, *TODOS),
    )


def cuerpo(e, fecha=FECHA, *, venta_a="15", entregado="830", agotado=False, **pagos):
    """A: cargada 20 = 15 vendidas + 3 devueltas + 2 merma (750). B: 10 vendidas (300)."""
    return {
        "fecha": fecha.isoformat(),
        "ruta_id": str(e.ruta.id),
        "lineas": [
            {
                "producto_id": str(e.pa.id),
                "cantidad_cargada": "20",
                "cantidad_vendida": venta_a,
                "cantidad_devuelta": str(20 - int(venta_a) - 2),
                "cantidad_merma": "2",
                "agotado": agotado,
            },
            {
                "producto_id": str(e.pb.id),
                "cantidad_cargada": "10",
                "cantidad_vendida": "10",
            },
        ],
        "pagos": {
            "efectivo": "800",
            "transferencia": "150",
            "credito": "100",
            "cobro_saldos": "50",
            "gastos": "20",
            "efectivo_entregado": entregado,
            **pagos,
        },
    }


def guardar(e, fecha=FECHA, **kw):
    r = e.c.post(URL, json=cuerpo(e, fecha, **kw), headers=e.h)
    assert r.status_code == 200, r.text
    return r.json()


def cerrar(e, liq_id):
    return e.c.post(f"{URL}/{liq_id}/cerrar", headers=e.h)


def ventas(e, fecha=FECHA):
    return list(
        e.db.scalars(
            select(VentaHistorica).where(
                VentaHistorica.ruta_id == e.ruta.id, VentaHistorica.fecha_venta == fecha
            )
        )
    )


def modelo(db) -> ModeloML:
    m = ModeloML(
        nombre=f"liq-{uuid.uuid4().hex[:6]}",
        algoritmo="xgboost",
        version="v1.0.1",
        ruta_artefacto="x",
        hash_artefacto="0" * 64,
        hiperparametros={},
        esquema_features={},
        ventana_desde=date(2025, 1, 1),
        ventana_hasta=date(2025, 3, 1),
        motivo_entrenamiento="manual",
    )
    db.add(m)
    db.flush()
    return m


def pronostico(e, m, producto, fecha=FECHA, valor="40") -> PronosticoDemanda:
    p = PronosticoDemanda(
        modelo_id=m.id,
        producto_id=producto.id,
        ruta_id=e.ruta.id,
        fecha_objetivo=fecha,
        horizonte_dias=1,
        demanda_predicha=Decimal(valor),
    )
    e.db.add(p)
    e.db.flush()
    return p


def jobs_en_cola(db):
    return list(
        db.scalars(
            select(JobML).where(
                JobML.tipo == TipoJob.EVALUACION_PRODUCCION, JobML.estado == EstadoJob.EN_COLA
            )
        )
    )


# ------------------------------------------------------------------ TC-LIQ-01 borrador
def test_borrador_no_afecta_ventas_lotes_ni_jobs(e):
    r = guardar(e)
    assert r["estado"] == "borrador" and r["version"] == 1 and r["lote_id"] is None
    assert Decimal(r["cuadre_dinero"]["venta_total"]) == Decimal("1050")
    assert r["cuadre_unidades"]["cuadra"] and r["devolucion_esperada"] == "3.00"
    assert ventas(e) == [] and jobs_en_cola(e.db) == []
    assert e.db.scalar(select(func.count()).select_from(EtlLote)) == 0
    # Reenviar actualiza el mismo borrador (idempotente por fecha/ruta/vendedor).
    otra = guardar(e, entregado="800")
    assert otra["id"] == r["id"]
    assert e.db.scalar(select(func.count()).select_from(LiquidacionDiaria)) == 1


def test_borrador_incompleto_se_guarda_con_advertencias_y_no_deja_cerrar(e):
    body = cuerpo(e)
    body["lineas"][0]["cantidad_devuelta"] = "0"  # faltan 3 unidades por justificar
    body["pagos"]["credito"] = "0"  # la venta no iguala los pagos
    r = e.c.post(URL, json=body, headers=e.h)
    assert r.status_code == 200
    assert len(r.json()["advertencias"]) >= 3  # sin carga + unidades + montos
    cierre = cerrar(e, r.json()["id"])
    assert cierre.status_code == 400 and cierre.json()["codigo"] == "UNIDADES_NO_CUADRAN"


# ------------------------------------------------------------------ TC-LIQ-02 cierre
def test_cierre_escribe_ventas_con_origen_liquidacion_y_lote_unico(e):
    liq = guardar(e)
    r = cerrar(e, liq["id"])
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cerrada" and r.json()["lote_id"]

    filas = {v.producto_id: v for v in ventas(e)}
    assert filas[e.pa.id].cantidad == 15 and filas[e.pa.id].monto_total == Decimal("750.00")
    assert filas[e.pb.id].precio_unitario == Decimal("30.00")
    assert all(v.vendedor_id == e.vendedor.id for v in filas.values())
    lote = e.db.get(EtlLote, filas[e.pa.id].lote_id)
    assert lote.origen == OrigenDatos.LIQUIDACION and lote.estado == EstadoLoteEtl.CARGADO
    assert len({v.lote_id for v in filas.values()}) == 1


def test_cierre_genera_comisiones_si_hay_porcentaje(e):
    parametro_repo.guardar_valor(e.db, "comisiones.porcentaje", 2)
    cerrar(e, guardar(e)["id"])
    comisiones = list(e.db.scalars(select(Comision)))
    assert sorted(c.monto for c in comisiones) == [Decimal("6.00"), Decimal("15.00")]


def test_cerrar_dos_veces_y_guardar_sobre_cerrada_son_409(e):
    liq = guardar(e)
    assert cerrar(e, liq["id"]).status_code == 200
    r = cerrar(e, liq["id"])
    assert r.status_code == 409 and r.json()["codigo"] == "LIQUIDACION_YA_CERRADA"
    r = e.c.post(URL, json=cuerpo(e), headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "LIQUIDACION_DUPLICADA"


def test_cerrar_exige_unidades_y_montos_cuadrados(e):
    body = cuerpo(e, credito="0")
    liq = e.c.post(URL, json=body, headers=e.h).json()
    r = cerrar(e, liq["id"])
    assert r.status_code == 400 and r.json()["codigo"] == "MONTOS_NO_CUADRAN"
    assert ventas(e) == [] and jobs_en_cola(e.db) == []


# ------------------------------------------------------------------ TC-LIQ-03/04 modelo
def test_cierre_llena_demanda_real_marca_censura_y_encola_una_evaluacion(e):
    m = modelo(e.db)
    pa, pb = pronostico(e, m, e.pa), pronostico(e, m, e.pb)
    cerrar(e, guardar(e, agotado=True)["id"])
    e.db.refresh(pa)
    e.db.refresh(pb)
    assert pa.demanda_real == 15 and pa.demanda_censurada is True
    assert pb.demanda_real == 10 and pb.demanda_censurada is False

    cola = jobs_en_cola(e.db)
    assert len(cola) == 1 and cola[0].parametros["origen"] == "liquidacion"
    # Otra liquidación seguida se coalesce en el mismo job.
    cerrar(e, guardar(e, FECHA - timedelta(days=1))["id"])
    assert len(jobs_en_cola(e.db)) == 1


def test_el_worker_procesa_la_evaluacion_en_cola_sin_entrenar(e):
    cerrar(e, guardar(e)["id"])
    job_id = job_service.procesar_evaluacion_en_cola(e.db)
    job = e.db.get(JobML, job_id)
    assert job.estado == EstadoJob.COMPLETADO
    assert job_service.procesar_evaluacion_en_cola(e.db) is None


def test_los_pronosticos_censurados_no_se_evaluan(e):
    m = modelo(e.db)
    pronostico(e, m, e.pa)
    pronostico(e, m, e.pb)
    cerrar(e, guardar(e, agotado=True)["id"])
    evaluables = forecast_repo.evaluables(e.db, m.id, FECHA, FECHA)
    assert [p for p, *_ in evaluables] == [e.pb.id]


def test_sin_liquidacion_no_hay_demanda_real_pasada_la_base_excel(e):
    """Un día sin liquidar no es demanda cero (ADR-14); sí lo es dentro de la base Excel."""
    m = modelo(e.db)
    p = pronostico(e, m, e.pa, FECHA)
    otro = pronostico(e, m, e.pa, FECHA - timedelta(days=5))
    cerrar(e, guardar(e, FECHA - timedelta(days=2))["id"])  # liquida otro día (hay ventas)
    forecast_repo.registrar_demanda_real(
        e.db, m.id, FECHA - timedelta(days=5), FECHA, ventas_hasta=FECHA
    )
    e.db.refresh(p)
    e.db.refresh(otro)
    assert p.demanda_real is None and otro.demanda_real is None
    # Con una base Excel que cubre ese día, la regla clásica (ausencia = 0) se mantiene.
    forecast_repo.registrar_demanda_real(
        e.db, m.id, FECHA - timedelta(days=5), FECHA, ventas_hasta=FECHA, ultima_fecha_excel=FECHA
    )
    e.db.refresh(p)
    assert p.demanda_real == 0


# ------------------------------------------------------------------ TC-LIQ-05 caja
def test_diferencia_de_caja_sobre_el_umbral_genera_alerta_y_no_bloquea(e):
    r = cerrar(e, guardar(e, entregado="800")["id"])  # esperado 830 -> faltante 30 > 10
    assert r.status_code == 200
    d = r.json()["cuadre_dinero"]
    assert Decimal(d["efectivo_esperado"]) == 830 and Decimal(d["diferencia_caja"]) == -30
    assert d["supera_umbral"] and r.json()["alerta_id"]
    alerta = e.db.get(Alerta, uuid.UUID(r.json()["alerta_id"]))
    assert alerta.tipo == TipoAlerta.DIFERENCIA_CAJA and "faltante" in alerta.mensaje


def test_diferencia_dentro_del_umbral_no_alerta(e):
    r = cerrar(e, guardar(e, entregado="825")["id"])
    assert r.json()["alerta_id"] is None
    assert e.db.scalar(select(func.count()).select_from(Alerta)) == 0


def test_umbral_configurable_y_alertas_visibles_para_el_gerente(e):
    r = e.c.put(f"{URL}/config", json={"umbral_diferencia_caja": "50"}, headers=e.h)
    assert r.status_code == 200 and e.c.get(f"{URL}/config", headers=e.h).json() == {
        "umbral_diferencia_caja": "50.00"
    }
    assert cerrar(e, guardar(e, entregado="800")["id"]).json()["alerta_id"] is None
    e.c.put(f"{URL}/config", json={"umbral_diferencia_caja": "5"}, headers=e.h)
    gerente = encabezados(e.admin, "alertas:leer", "liquidaciones:leer")
    assert e.c.get("/api/v1/alerts", headers=gerente).status_code == 200


# ------------------------------------------------------------------ TC-LIQ-06/07 validaciones
def test_validaciones_de_entrada(e):
    def post(body):
        return e.c.post(URL, json=body, headers=e.h)

    manana = date.today() + timedelta(days=1)
    r = post(cuerpo(e, manana))
    assert r.status_code == 400 and r.json()["codigo"] == "VENTA_FECHA_FUTURA"

    body = cuerpo(e)
    body["lineas"].append(body["lineas"][0])
    assert post(body).json()["codigo"] == "PRODUCTO_DUPLICADO_EN_CIERRE"

    body = cuerpo(e)
    body["lineas"][0]["cantidad_vendida"] = "19"  # 19 + 3 + 2 > 20
    assert post(body).json()["codigo"] == "UNIDADES_NO_CUADRAN"

    body = cuerpo(e)
    body["lineas"] = [
        {"producto_id": str(e.pa.id), "cantidad_cargada": "0", "cantidad_vendida": "0"}
    ]
    assert post(body).json()["codigo"] == "LIQUIDACION_SIN_MOVIMIENTO"

    body = cuerpo(e)
    body["lineas"][0]["cantidad_vendida"] = "-1"
    assert post(body).status_code == 422

    e.pb.activo = False
    e.db.flush()
    assert post(cuerpo(e)).json()["codigo"] == "PRODUCTO_INACTIVO"
    e.pb.activo = True
    e.ruta.activa = False
    e.db.flush()
    assert post(cuerpo(e)).json()["codigo"] == "RUTA_INACTIVA"


# ------------------------------------------------------------------ TC-LIQ-08 corregir
def test_corregir_sube_version_hace_upsert_y_recalcula_sin_duplicar(e):
    m = modelo(e.db)
    pa, pb = pronostico(e, m, e.pa), pronostico(e, m, e.pb)
    liq = guardar(e)
    cerrar(e, liq["id"])
    e.db.execute(JobML.__table__.delete())  # vacía la cola para comprobar el reencolado

    body = {**cuerpo(e, venta_a="16", entregado="830"), "motivo": "se contó mal"}
    body["lineas"].pop()  # B deja de venderse
    body["pagos"].update(efectivo="800", transferencia="0", credito="0")
    r = e.c.post(f"{URL}/{liq['id']}/corregir", json=body, headers=e.h)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and r.json()["estado"] == "cerrada"

    filas = ventas(e)
    assert [(v.producto_id, v.cantidad) for v in filas] == [(e.pa.id, 16)]
    assert len({v.lote_id for v in filas}) == 1
    e.db.refresh(pa)
    e.db.refresh(pb)
    assert pa.demanda_real == 16 and pb.demanda_real == 0
    assert len(jobs_en_cola(e.db)) == 1
    historial = e.db.get(LiquidacionDiaria, uuid.UUID(liq["id"])).historial
    assert [h["accion"] for h in historial] == ["creada", "cerrada", "corregida"]
    assert historial[-1]["motivo"] == "se contó mal" and historial[-1]["antes"]["version"] == 1


def test_corregir_exige_cerrada_motivo_y_misma_clave(e):
    liq = guardar(e)
    body = {**cuerpo(e), "motivo": "motivo valido"}
    r = e.c.post(f"{URL}/{liq['id']}/corregir", json=body, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "LIQUIDACION_NO_CERRADA"
    cerrar(e, liq["id"])
    sin_motivo = {k: v for k, v in body.items() if k != "motivo"}
    assert e.c.post(f"{URL}/{liq['id']}/corregir", json=sin_motivo, headers=e.h).status_code == 422
    otro_dia = {**cuerpo(e, FECHA - timedelta(days=3)), "motivo": "motivo valido"}
    r = e.c.post(f"{URL}/{liq['id']}/corregir", json=otro_dia, headers=e.h)
    assert r.json()["codigo"] == "CORRECCION_CAMBIA_CLAVE"


# ------------------------------------------------------------------ TC-LIQ-09 anular
def test_anular_revierte_ventas_demanda_real_y_libera_el_lote(e):
    m = modelo(e.db)
    pa = pronostico(e, m, e.pa)
    liq = guardar(e, entregado="800")
    cerrar(e, liq["id"])
    r = e.c.post(f"{URL}/{liq['id']}/anular", json={"motivo": "día duplicado"}, headers=e.h)
    assert r.status_code == 200 and r.json()["estado"] == "anulada"
    assert ventas(e) == []
    e.db.refresh(pa)
    assert pa.demanda_real is None
    lote = e.db.get(EtlLote, uuid.UUID(r.json()["lote_id"]))
    assert lote.estado == EstadoLoteEtl.RECHAZADO
    abierta = e.db.scalars(select(Alerta).where(Alerta.estado == "abierta")).all()
    assert abierta == []

    otra = e.c.post(f"{URL}/{liq['id']}/anular", json={"motivo": "otra vez"}, headers=e.h)
    assert otra.status_code == 409 and otra.json()["codigo"] == "LIQUIDACION_YA_ANULADA"
    assert cerrar(e, liq["id"]).json()["codigo"] == "LIQUIDACION_YA_ANULADA"

    # La misma fecha/ruta/vendedor con idénticas líneas puede liquidarse de nuevo.
    nueva = guardar(e, entregado="800")
    assert nueva["id"] != liq["id"] and cerrar(e, nueva["id"]).status_code == 200
    assert len(ventas(e)) == 2


def test_anular_un_borrador_no_toca_ventas(e):
    liq = guardar(e)
    r = e.c.post(f"{URL}/{liq['id']}/anular", json={"motivo": "no se usará"}, headers=e.h)
    assert r.status_code == 200 and r.json()["lote_id"] is None


# ------------------------------------------------------------------ TC-LIQ-10 RBAC
@pytest.mark.parametrize(
    ("metodo", "ruta", "permiso"),
    [
        ("post", "", "liquidaciones:registrar"),
        ("get", "/precarga", "liquidaciones:registrar"),
        ("get", "", "liquidaciones:leer"),
        ("get", f"/{uuid.uuid4()}", "liquidaciones:leer"),
        ("post", f"/{uuid.uuid4()}/cerrar", "liquidaciones:cerrar"),
        ("post", f"/{uuid.uuid4()}/corregir", "liquidaciones:corregir"),
        ("post", f"/{uuid.uuid4()}/anular", "liquidaciones:corregir"),
        ("put", "/config", "liquidaciones:corregir"),
    ],
)
def test_rbac_401_sin_sesion_y_403_sin_el_permiso(e, metodo, ruta, permiso):
    llamar = getattr(e.c, metodo)
    assert llamar(URL + ruta).status_code == 401
    otros = tuple(p for p in TODOS if p != permiso)
    r = llamar(URL + ruta, headers=encabezados(e.admin, *otros, "alertas:leer"))
    assert r.status_code == 403 and r.json()["codigo"] == "PERMISO_DENEGADO"


def test_gerente_lee_pero_no_registra_ni_cierra(e):
    liq = guardar(e)
    g = encabezados(e.admin, "liquidaciones:leer")
    assert e.c.get(f"{URL}/{liq['id']}", headers=g).status_code == 200
    assert e.c.post(URL, json=cuerpo(e), headers=g).status_code == 403
    assert e.c.post(f"{URL}/{liq['id']}/cerrar", headers=g).status_code == 403


# ------------------------------------------------------------------ consultas
def test_listado_filtra_pagina_y_detalle_404(e):
    a = guardar(e)
    b = guardar(e, FECHA - timedelta(days=1))
    cerrar(e, b["id"])
    todo = e.c.get(URL, headers=e.h).json()
    assert todo["total"] == 2 and todo["liquidaciones"][0]["id"] == a["id"]  # más reciente primero
    assert todo["liquidaciones"][0]["ruta_nombre"] == "Cornelio"
    cerradas = e.c.get(URL, params={"estado": "cerrada"}, headers=e.h).json()
    assert [x["id"] for x in cerradas["liquidaciones"]] == [b["id"]]
    pag = e.c.get(URL, params={"limit": 1, "offset": 1}, headers=e.h).json()
    assert pag["total"] == 2 and len(pag["liquidaciones"]) == 1
    rango = e.c.get(URL, params={"desde": FECHA.isoformat()}, headers=e.h).json()
    assert rango["total"] == 1
    malo = e.c.get(URL, params={"desde": "2026-09-05", "hasta": "2026-09-01"}, headers=e.h)
    assert malo.status_code == 422
    assert e.c.get(f"{URL}/{uuid.uuid4()}", headers=e.h).status_code == 404


# ------------------------------------------------------------------ TC-LIQ-11 carga despachada
def _carga(e, estado=EstadoCarga.DESPACHADA, a="20", b="10"):
    m = modelo(e.db)
    carga = CargaRuta(
        ruta_id=e.ruta.id,
        fecha_operacion=FECHA,
        estado=estado,
        modelo_id=m.id,
        generado_por=e.admin.id,
        aprobado_por=e.admin.id,
        aprobada_en=func.now(),
    )
    carga.detalles = [
        DetalleCarga(
            producto_id=p.id,
            cantidad_predicha=Decimal(q),
            stock_disponible_al_generar=Decimal(q),
            cantidad_sugerida=Decimal(q),
            cantidad_aprobada=Decimal(q),
        )
        for p, q in ((e.pa, a), (e.pb, b))
    ]
    e.db.add(carga)
    e.db.flush()
    return carga


def test_precarga_parte_de_la_carga_despachada(e):
    carga = _carga(e)
    r = e.c.get(
        f"{URL}/precarga",
        params={"fecha": FECHA.isoformat(), "ruta_id": str(e.ruta.id)},
        headers=e.h,
    ).json()
    assert r["carga_id"] == str(carga.id) and r["advertencias"] == []
    assert {x["producto_id"]: Decimal(x["cantidad_cargada"]) for x in r["lineas"]} == {
        str(e.pa.id): 20,
        str(e.pb.id): 10,
    }
    assert r["liquidacion"] is None


def test_precarga_sin_carga_advierte_y_trae_la_liquidacion_vigente(e):
    guardar(e)
    r = e.c.get(
        f"{URL}/precarga",
        params={"fecha": FECHA.isoformat(), "ruta_id": str(e.ruta.id)},
        headers=e.h,
    ).json()
    assert r["carga_id"] is None and r["advertencias"]
    assert r["liquidacion"]["estado"] == "borrador"


def test_editar_lo_cargado_exige_justificacion_si_hay_carga_despachada(e):
    _carga(e, a="25")  # se despacharon 25; la liquidación dice 20
    r = e.c.post(URL, json=cuerpo(e), headers=e.h)
    assert r.status_code == 400 and r.json()["codigo"] == "CARGA_REQUIERE_JUSTIFICACION"
    body = cuerpo(e)
    body["lineas"][0]["justificacion_carga"] = "5 cajas se quedaron en bodega"
    ok = e.c.post(URL, json=body, headers=e.h)
    assert ok.status_code == 200 and ok.json()["lineas"][1]["justificacion_carga"] is None


# ------------------------------------------------------------------ TC-LIQ-12 línea base Excel
def test_no_se_pisan_ventas_de_la_base_excel(e):
    lote = EtlLote(
        usuario_id=e.admin.id, archivo_nombre="marzo.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    e.db.add(lote)
    e.db.flush()
    e.db.add(
        VentaHistorica(
            lote_id=lote.id,
            fecha_venta=FECHA,
            producto_id=e.pa.id,
            ruta_id=e.ruta.id,
            vendedor_id=e.vendedor.id,
            cantidad=Decimal(9),
            precio_unitario=Decimal(50),
            monto_total=Decimal(450),
        )
    )
    e.db.flush()
    r = cerrar(e, guardar(e)["id"])
    assert r.status_code == 409 and r.json()["codigo"] == "VENTAS_EXCEL_EXISTENTES"
    assert ventas(e)[0].cantidad == 9


# ------------------------------------------------------------------ TC-LIQ-13 puerta del ETL
def test_excel_deshabilitado_tras_cerrar_el_arranque(e):
    etl = "/api/v1/etl"
    h_etl = encabezados(e.admin, "etl:cargar", "etl:configurar")
    assert e.c.get(f"{etl}/config", headers=h_etl).json() == {
        "carga_excel_habilitada": True,
        "fuente_reentrenamiento": "excel_mas_liquidacion",
    }
    solo_cargar = encabezados(e.admin, "etl:cargar")
    cierre = {"carga_excel_habilitada": False, "fuente_reentrenamiento": "excel_mas_liquidacion"}
    assert e.c.put(f"{etl}/config", json=cierre, headers=solo_cargar).status_code == 403
    assert e.c.put(f"{etl}/config", json=cierre, headers=h_etl).status_code == 200

    archivo = {"file": ("ventas.xlsx", b"PK\x03\x04", "application/octet-stream")}
    r = e.c.post(f"{etl}/upload-excel", files=archivo, headers=solo_cargar)
    assert r.status_code == 409 and r.json()["codigo"] == "EXCEL_DESHABILITADO"
    assert e.db.scalar(select(func.count()).select_from(EtlLote)) == 0

    cierre["carga_excel_habilitada"] = True  # reabrir restablece el comportamiento previo
    e.c.put(f"{etl}/config", json=cierre, headers=h_etl)
    r = e.c.post(f"{etl}/upload-excel", files=archivo, headers=solo_cargar)
    assert r.json()["codigo"] == "ARCHIVO_INVALIDO"


def test_el_historial_etl_no_lista_lotes_de_liquidacion(e):
    cerrar(e, guardar(e)["id"])
    h = encabezados(e.admin, "etl:cargar")
    assert e.c.get("/api/v1/etl/batches", headers=h).json()["total"] == 0
