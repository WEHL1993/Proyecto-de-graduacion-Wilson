"""Planificación de carga de ruta contra PostgreSQL real: TC-LOAD-01..04, TC-RBAC-02, kardex.

Requiere la BD migrada; se omiten si no hay conexión. La predicción se sustituye por un doble
con demandas fijas (la inferencia real se prueba en `test_predictions.py`). Cada prueba corre en
una transacción que se revierte al final.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password
from app.domain.enums import EstadoCarga, TipoAlerta, TipoMovimiento
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Categoria, Inventario, Kardex, Producto, Ruta
from app.domain.models.ml import Alerta, ModeloML
from app.domain.models.operations import CargaRuta
from app.domain.models.sales import EtlLote, VentaHistorica
from app.main import app
from app.repositories import carga_repo
from app.schemas.predictions import (
    DemandModelInfo,
    DemandPoint,
    DemandProductForecast,
    DemandResponse,
)
from app.services import inventory_service, load_plan_service

URL = "/api/v1/routes/load-plans"
FECHA = date(2025, 4, 1)
VENTAS = "carga_ruta:generar", "carga_ruta:aprobar", "inventario:leer"


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
def entorno(db_session, monkeypatch):
    """Escenario TC-LOAD-01: ruta R-04, producto A (stock 150) y B (stock 0), modelo activo."""
    db = db_session
    sufijo = uuid.uuid4().hex[:6]
    usuario = Usuario(
        email=f"ventas-{sufijo}@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo="Ventas",
    )
    categoria = Categoria(nombre=f"cat-{sufijo}")
    ruta = Ruta(codigo=f"R-{sufijo}", nombre="R-04")
    db.add_all([usuario, categoria, ruta])
    db.flush()
    lote = EtlLote(
        usuario_id=usuario.id, archivo_nombre="load.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    prod_a = Producto(sku=f"A-{sufijo}", nombre="Producto A", categoria_id=categoria.id)
    prod_b = Producto(sku=f"B-{sufijo}", nombre="Producto B", categoria_id=categoria.id)
    modelo = ModeloML(
        nombre=f"demanda-{sufijo}",
        algoritmo="xgboost",
        version="v1.0.1",
        ruta_artefacto="models/xgboost/v1.0.1",
        hash_artefacto="0" * 64,
        hiperparametros={},
        esquema_features=[],
        ventana_desde=date(2025, 1, 1),
        ventana_hasta=date(2025, 3, 31),
        motivo_entrenamiento="manual",
    )
    db.add_all([lote, prod_a, prod_b, modelo])
    db.flush()
    db.add_all(
        [
            Inventario(producto_id=prod_a.id, stock_actual=Decimal("150")),
            Inventario(producto_id=prod_b.id, stock_actual=Decimal("0")),
            *(
                VentaHistorica(
                    lote_id=lote.id,
                    fecha_venta=FECHA - timedelta(days=1),
                    producto_id=p.id,
                    ruta_id=ruta.id,
                    cantidad=Decimal("10"),
                    precio_unitario=Decimal("10.00"),
                    monto_total=Decimal("100.00"),
                )
                for p in (prod_a, prod_b)
            ),
        ]
    )
    db.commit()

    demandas = {prod_a.id: 210.0, prod_b.id: 60.0}
    solicitudes: list = []

    def predecir_falso(_db, solicitud):
        solicitudes.append(solicitud)
        return DemandResponse(
            modelo=DemandModelInfo(id=modelo.id, algoritmo="xgboost", version="v1.0.1"),
            generado_en=datetime.now(UTC),
            pronosticos=[
                DemandProductForecast(
                    producto_id=pid,
                    serie=[
                        DemandPoint(
                            fecha_objetivo=solicitud.fecha_base + timedelta(days=1),
                            demanda_predicha=demandas[pid],
                        )
                    ],
                )
                for pid in solicitud.producto_ids
            ],
        )

    monkeypatch.setattr(load_plan_service.prediction_service, "predecir_demanda", predecir_falso)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield SimpleNamespace(
            db=db,
            client=TestClient(app),
            usuario=usuario,
            ruta=ruta,
            a=prod_a,
            b=prod_b,
            modelo=modelo,
            solicitudes=solicitudes,
        )
    finally:
        app.dependency_overrides.clear()


def _headers(usuario: Usuario, *permisos: str) -> dict[str, str]:
    token, _ = create_access_token(sub=str(usuario.id), roles=[], perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}


def _generar(e, **extra):
    cuerpo = {"accion": "generar", "ruta_id": str(e.ruta.id), "fecha_operacion": str(FECHA)}
    return e.client.post(URL, json={**cuerpo, **extra}, headers=_headers(e.usuario, *VENTAS))


def _decidir(e, accion: str, carga_id, permisos=VENTAS, **extra):
    return e.client.post(
        URL,
        json={"accion": accion, "carga_id": str(carga_id), **extra},
        headers=_headers(e.usuario, *permisos),
    )


def _carga_pendiente(e) -> str:
    """Genera un plan y lo deja en `pendiente_aprobacion` (estado de partida de TC-LOAD-02/03)."""
    r = _generar(e)
    assert r.status_code == 200, r.text
    carga_id = r.json()["carga_id"]
    carga = e.db.get(CargaRuta, uuid.UUID(carga_id))
    carga.estado = EstadoCarga.PENDIENTE_APROBACION
    e.db.commit()
    return carga_id


def _items(cuerpo: dict) -> dict[str, dict]:
    return {i["sku"]: i for i in cuerpo["items"]}


def _movimientos(e, tipo: TipoMovimiento | None = None) -> list[Kardex]:
    stmt = select(Kardex).where(Kardex.producto_id.in_([e.a.id, e.b.id]))
    if tipo:
        stmt = stmt.where(Kardex.tipo_movimiento == tipo)
    return list(e.db.scalars(stmt.order_by(Kardex.id)))


def _inventario(e, producto: Producto) -> Inventario:
    e.db.expire_all()
    return e.db.scalars(select(Inventario).where(Inventario.producto_id == producto.id)).one()


# ------------------------------------------------------------------ TC-LOAD-01
def test_tc_load_01_generar_aplica_min_demanda_stock(entorno):
    e = entorno
    r = _generar(e)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "borrador"
    assert cuerpo["modelo_id"] == str(e.modelo.id)

    items = _items(cuerpo)
    a, b = items[e.a.sku], items[e.b.sku]
    assert (a["cantidad_predicha"], a["stock_disponible"]) == ("210.00", "150.00")
    assert (a["cantidad_sugerida"], a["ajustado_por_stock"]) == ("150.00", True)
    assert (b["cantidad_predicha"], b["stock_disponible"]) == ("60.00", "0.00")
    assert (b["cantidad_sugerida"], b["ajustado_por_stock"]) == ("0.00", True)
    assert all(i["cantidad_aprobada"] is None for i in cuerpo["items"])
    for i in cuerpo["items"]:  # sugerida = min(predicha, disponible) en todas las filas
        assert Decimal(i["cantidad_sugerida"]) == min(
            Decimal(i["cantidad_predicha"]), Decimal(i["stock_disponible"])
        )

    # predice la fecha de operación: horizonte 1 desde el día anterior, para la ruta
    (solicitud,) = e.solicitudes
    assert solicitud.ruta_id == e.ruta.id and solicitud.horizonte_dias == 1
    assert solicitud.fecha_base == FECHA - timedelta(days=1)

    alertas = {
        a.producto_id: a
        for a in e.db.scalars(select(Alerta).where(Alerta.producto_id.in_([e.a.id, e.b.id])))
    }
    assert alertas[e.b.id].tipo == TipoAlerta.QUIEBRE_PROYECTADO
    assert alertas[e.a.id].tipo == TipoAlerta.STOCK_BAJO
    assert set(cuerpo["alertas_generadas"]) == {str(a.id) for a in alertas.values()}
    assert _movimientos(e) == []  # generar no toca inventario ni kardex


def test_generar_con_stock_suficiente_no_ajusta_ni_alerta(entorno):
    e = entorno
    inv = _inventario(e, e.a)
    inv.stock_actual = Decimal("500")
    inv.stock_reservado = Decimal("100")  # disponible = 400 ≥ 210
    e.db.commit()

    cuerpo = _generar(e).json()
    a = _items(cuerpo)[e.a.sku]
    assert (a["stock_disponible"], a["cantidad_sugerida"], a["ajustado_por_stock"]) == (
        "400.00",
        "210.00",
        False,
    )
    assert all(
        e.db.get(Alerta, uuid.UUID(i)).producto_id != e.a.id for i in cuerpo["alertas_generadas"]
    )


# ------------------------------------------------------------------ TC-LOAD-02
def test_tc_load_02_aprobar_sobre_stock_es_400_sin_efectos(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    r = _decidir(
        e, "aprobar", carga_id, ajustes=[{"producto_id": str(e.a.id), "cantidad_aprobada": 200}]
    )
    assert r.status_code == 400, r.text
    assert r.json()["codigo"] == "CANTIDAD_EXCEDE_STOCK"

    e.db.expire_all()
    carga = e.db.get(CargaRuta, uuid.UUID(carga_id))
    assert carga.estado == EstadoCarga.PENDIENTE_APROBACION
    assert carga.aprobado_por is None and carga.aprobada_en is None
    assert all(d.cantidad_aprobada is None for d in carga.detalles)
    assert _movimientos(e) == []
    assert _inventario(e, e.a).stock_reservado == 0


def test_aprobar_revalida_contra_el_stock_actual(entorno):
    """Otra carga pudo reservar stock después de generar el plan."""
    e = entorno
    carga_id = _carga_pendiente(e)
    inv = _inventario(e, e.a)
    inv.stock_reservado = Decimal("100")  # disponible actual = 50 < 150 sugeridas
    e.db.commit()

    r = _decidir(e, "aprobar", carga_id)
    assert (r.status_code, r.json()["codigo"]) == (400, "CANTIDAD_EXCEDE_STOCK")
    assert e.db.get(CargaRuta, uuid.UUID(carga_id)).estado == EstadoCarga.PENDIENTE_APROBACION
    assert _movimientos(e) == []


# ------------------------------------------------------------------ TC-LOAD-03
def test_tc_load_03_aprobar_reserva_stock_y_registra_kardex(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    r = _decidir(
        e, "aprobar", carga_id, ajustes=[{"producto_id": str(e.a.id), "cantidad_aprobada": 100}]
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "aprobada"
    items = _items(cuerpo)
    assert items[e.a.sku]["cantidad_aprobada"] == "100.00"
    assert items[e.b.sku]["cantidad_aprobada"] == "0.00"  # sin ajuste: aprueba lo sugerido

    e.db.expire_all()
    carga = e.db.get(CargaRuta, uuid.UUID(carga_id))
    assert carga.aprobado_por == e.usuario.id and carga.aprobada_en is not None

    inv_a = _inventario(e, e.a)
    assert (inv_a.stock_actual, inv_a.stock_reservado) == (150, 100)
    assert inv_a.stock_disponible == 50
    assert _inventario(e, e.b).stock_reservado == 0

    (reserva,) = _movimientos(e)  # B aprobó 0: sin movimiento
    assert reserva.tipo_movimiento == TipoMovimiento.RESERVA
    assert (reserva.producto_id, reserva.cantidad) == (e.a.id, 100)
    assert reserva.saldo_resultante == 150  # saldo físico: la reserva no lo altera
    assert (reserva.referencia_tipo, reserva.referencia_id) == ("carga_ruta", carga.id)
    assert reserva.usuario_id == e.usuario.id


def test_aprobar_sin_ajustes_aprueba_lo_sugerido(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    assert _decidir(e, "aprobar", carga_id).status_code == 200
    assert _inventario(e, e.a).stock_reservado == 150


def test_aprobar_desde_borrador_y_no_dos_veces(entorno):
    e = entorno
    carga_id = _generar(e).json()["carga_id"]  # borrador
    assert _decidir(e, "aprobar", carga_id).status_code == 200
    r = _decidir(e, "aprobar", carga_id)
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_CARGA_INVALIDO")
    assert len(_movimientos(e, TipoMovimiento.RESERVA)) == 1  # no reservó dos veces


def test_ajuste_de_producto_ajeno_o_carga_inexistente(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    r = _decidir(
        e, "aprobar", carga_id, ajustes=[{"producto_id": str(uuid.uuid4()), "cantidad_aprobada": 1}]
    )
    assert (r.status_code, r.json()["codigo"]) == (400, "PRODUCTO_FUERA_DE_CARGA")
    r = _decidir(e, "aprobar", uuid.uuid4())
    assert (r.status_code, r.json()["codigo"]) == (400, "CARGA_NO_ENCONTRADA")


# ------------------------------------------------------------------ TC-LOAD-04
def test_tc_load_04_carga_vigente_existente(entorno):
    e = entorno
    assert _generar(e).status_code == 200
    r = _generar(e)
    assert (r.status_code, r.json()["codigo"]) == (400, "CARGA_VIGENTE_EXISTENTE")
    cantidad = e.db.scalar(
        select(func.count()).select_from(CargaRuta).where(CargaRuta.ruta_id == e.ruta.id)
    )
    assert cantidad == 1


def test_carga_vigente_bloqueada_por_el_indice_unico_ante_carrera(entorno, monkeypatch):
    """Si la pre-verificación no ve la carga (otra transacción la creó), decide el índice."""
    e = entorno
    assert _generar(e).status_code == 200
    monkeypatch.setattr(carga_repo, "vigente_de_ruta", lambda *args: None)
    r = _generar(e)
    assert (r.status_code, r.json()["codigo"]) == (400, "CARGA_VIGENTE_EXISTENTE")


def test_carga_rechazada_libera_el_cupo_de_la_ruta_y_fecha(entorno):
    e = entorno
    carga_id = _generar(e).json()["carga_id"]
    assert _decidir(e, "rechazar", carga_id, motivo_rechazo="Ruta cancelada").status_code == 200
    assert _generar(e).status_code == 200


# ------------------------------------------------------------------ rechazar
def test_rechazar_exige_motivo(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    for extra in ({}, {"motivo_rechazo": "   "}):
        assert _decidir(e, "rechazar", carga_id, **extra).status_code == 422
    assert e.db.get(CargaRuta, uuid.UUID(carga_id)).estado == EstadoCarga.PENDIENTE_APROBACION


def test_rechazar_pendiente_registra_motivo_sin_tocar_inventario(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    r = _decidir(e, "rechazar", carga_id, motivo_rechazo="Demanda irreal")
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    carga = e.db.get(CargaRuta, uuid.UUID(carga_id))
    assert "Demanda irreal" in carga.observaciones
    assert _movimientos(e) == []


def test_rechazar_aprobada_libera_reservas_y_registra_kardex(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    assert _decidir(e, "aprobar", carga_id).status_code == 200
    assert _inventario(e, e.a).stock_reservado == 150

    r = _decidir(e, "rechazar", carga_id, motivo_rechazo="Camión averiado")
    assert r.status_code == 200 and r.json()["estado"] == "rechazada"
    assert _inventario(e, e.a).stock_reservado == 0
    (liberacion,) = _movimientos(e, TipoMovimiento.LIBERACION)
    assert (liberacion.producto_id, liberacion.cantidad) == (e.a.id, 150)


def test_no_se_decide_una_carga_rechazada_ni_despachada(entorno):
    e = entorno
    carga_id = _generar(e).json()["carga_id"]
    assert _decidir(e, "rechazar", carga_id, motivo_rechazo="x").status_code == 200
    for accion, extra in (("aprobar", {}), ("rechazar", {"motivo_rechazo": "y"})):
        r = _decidir(e, accion, carga_id, **extra)
        assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_CARGA_INVALIDO")

    otra = _generar(e).json()["carga_id"]
    despachada = e.db.get(CargaRuta, uuid.UUID(otra))
    despachada.aprobado_por, despachada.aprobada_en = e.usuario.id, datetime.now(UTC)
    despachada.estado = EstadoCarga.DESPACHADA  # después: la CHECK exige aprobación completa
    e.db.commit()
    r = _decidir(e, "rechazar", otra, motivo_rechazo="z")
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_CARGA_INVALIDO")


# ------------------------------------------------------------------ validación y RBAC
@pytest.mark.parametrize(
    "cuerpo",
    [
        {"accion": "generar"},
        {"accion": "generar", "ruta_id": str(uuid.uuid4())},
        {"accion": "aprobar"},
        {"accion": "borrar", "carga_id": str(uuid.uuid4())},
        {"accion": "rechazar", "carga_id": str(uuid.uuid4()), "ajustes": []},
    ],
)
def test_solicitud_incompleta_es_422(entorno, cuerpo):
    r = entorno.client.post(URL, json=cuerpo, headers=_headers(entorno.usuario, *VENTAS))
    assert r.status_code == 422


def test_ajuste_negativo_o_repetido_es_422(entorno):
    e = entorno
    carga_id = str(uuid.uuid4())
    pid = str(e.a.id)
    negativo = [{"producto_id": pid, "cantidad_aprobada": -1}]
    repetido = [{"producto_id": pid, "cantidad_aprobada": 1}] * 2
    for ajustes in (negativo, repetido):
        assert _decidir(e, "aprobar", carga_id, ajustes=ajustes).status_code == 422


def test_tc_rbac_02_compras_no_puede_aprobar(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    r = _decidir(e, "aprobar", carga_id, permisos=("prediccion:consultar", "inventario:leer"))
    assert r.status_code == 403 and r.json()["codigo"] == "PERMISO_DENEGADO"
    assert e.db.get(CargaRuta, uuid.UUID(carga_id)).estado == EstadoCarga.PENDIENTE_APROBACION
    assert _movimientos(e) == []


def test_permisos_por_accion_y_sin_token(entorno):
    e = entorno
    cuerpo = {"accion": "generar", "ruta_id": str(e.ruta.id), "fecha_operacion": str(FECHA)}
    assert e.client.post(URL, json=cuerpo).status_code == 401
    solo_aprobar = _headers(e.usuario, "carga_ruta:aprobar")
    assert e.client.post(URL, json=cuerpo, headers=solo_aprobar).status_code == 403
    carga_id = _generar(e).json()["carga_id"]
    solo_generar = _headers(e.usuario, "carga_ruta:generar")
    r = e.client.post(
        URL,
        json={"accion": "rechazar", "carga_id": carga_id, "motivo_rechazo": "m"},
        headers=solo_generar,
    )
    assert r.status_code == 403


def test_ruta_inexistente_o_sin_productos(entorno):
    e = entorno
    r = _generar(e, ruta_id=str(uuid.uuid4()))
    assert (r.status_code, r.json()["codigo"]) == (400, "RUTA_NO_ENCONTRADA")
    vacia = Ruta(codigo=f"V-{uuid.uuid4().hex[:6]}", nombre="Sin ventas")
    e.db.add(vacia)
    e.db.commit()
    r = _generar(e, ruta_id=str(vacia.id))
    assert (r.status_code, r.json()["codigo"]) == (400, "RUTA_SIN_PRODUCTOS")


# ------------------------------------------------------------------ inventario y kardex
def test_endpoints_de_existencias_y_kardex(entorno):
    e = entorno
    carga_id = _carga_pendiente(e)
    assert _decidir(e, "aprobar", carga_id).status_code == 200
    h = _headers(e.usuario, "inventario:leer")

    r = e.client.get("/api/v1/inventory", params={"producto_id": str(e.a.id)}, headers=h)
    assert r.status_code == 200, r.text
    (item,) = r.json()["items"]
    assert (item["stock_actual"], item["stock_reservado"], item["stock_disponible"]) == (
        "150.00",
        "150.00",
        "0.00",
    )

    r = e.client.get("/api/v1/inventory/kardex", params={"producto_id": str(e.a.id)}, headers=h)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["tipo_movimiento"] == "reserva"
    assert cuerpo["items"][0]["referencia_id"] == carga_id

    r = e.client.get(
        "/api/v1/inventory/kardex",
        params={"tipo_movimiento": "salida", "producto_id": str(e.a.id)},
        headers=h,
    )
    assert r.json()["total"] == 0

    assert e.client.get("/api/v1/inventory").status_code == 401
    sin_permiso = _headers(e.usuario, "etl:cargar")
    assert e.client.get("/api/v1/inventory", headers=sin_permiso).status_code == 403
    assert e.client.get("/api/v1/inventory", params={"limit": 0}, headers=h).status_code == 422


def test_existencias_bajo_minimo_y_producto_sin_inventario(entorno):
    e = entorno
    e.b.stock_minimo = Decimal("5")
    sin_fila = Producto(
        sku=f"S-{uuid.uuid4().hex[:6]}", nombre="Sin inventario", categoria_id=e.a.categoria_id
    )
    e.db.add(sin_fila)
    e.db.commit()
    h = _headers(e.usuario, "inventario:leer")

    r = e.client.get("/api/v1/inventory", params={"producto_id": str(sin_fila.id)}, headers=h)
    assert r.json()["items"][0]["stock_actual"] == "0.00"

    r = e.client.get("/api/v1/inventory", params={"bajo_minimo": True, "limit": 200}, headers=h)
    skus = {i["sku"] for i in r.json()["items"]}
    assert e.b.sku in skus and e.a.sku not in skus  # B: disponible 0 < mínimo 5


def test_stock_disponible_y_salida_fisica_de_despacho(entorno):
    e = entorno
    carga_id = uuid.UUID(_carga_pendiente(e))
    assert _decidir(e, "aprobar", carga_id).status_code == 200
    desconocido = uuid.uuid4()  # sin fila de inventario: disponible 0
    disp = inventory_service.stock_disponible(e.db, [e.a.id, e.b.id, desconocido])
    assert (disp[e.a.id], disp[e.b.id], disp[desconocido]) == (0, 0, 0)

    inventory_service.confirmar_salida(
        e.db, {e.a.id: Decimal("150")}, referencia_id=carga_id, usuario_id=e.usuario.id
    )
    inv = _inventario(e, e.a)
    assert (inv.stock_actual, inv.stock_reservado) == (0, 0)
    (salida,) = _movimientos(e, TipoMovimiento.SALIDA)
    assert (salida.cantidad, salida.saldo_resultante) == (150, 0)

    with pytest.raises(AppError) as exc:
        inventory_service.confirmar_salida(
            e.db, {e.a.id: Decimal("1")}, referencia_id=carga_id, usuario_id=e.usuario.id
        )
    assert exc.value.codigo == "STOCK_INSUFICIENTE"
