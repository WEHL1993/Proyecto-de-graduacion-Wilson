"""Abastecimiento contra PostgreSQL real: sugerencias, ciclo de pedido y recepción en kardex.

Requiere la BD migrada; se omiten si no hay conexión. La predicción se sustituye por un doble con
demandas fijas por producto. Cada prueba corre en una transacción que se revierte al final.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password
from app.domain.enums import TipoMovimiento
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Categoria, Inventario, Kardex, Producto, Proveedor
from app.main import app
from app.schemas.predictions import (
    DemandModelInfo,
    DemandPoint,
    DemandProductForecast,
    DemandResponse,
)
from app.services import purchasing_service

BASE = "/api/v1/purchasing"
COMPRAS = ("pedido_proveedor:gestionar", "inventario:leer")
BODEGA = ("inventario:ajustar", "inventario:leer", "carga_ruta:despachar")
PROVEEDOR = ("pedido_proveedor:confirmar",)
MANANA = date.today() + timedelta(days=1)


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


def _usuario(db: Session, nombre: str, proveedor: Proveedor | None = None) -> Usuario:
    usuario = Usuario(
        email=f"{nombre}-{uuid.uuid4().hex[:8]}@ds.gt",
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo=nombre,
        proveedor_id=proveedor.id if proveedor else None,
    )
    db.add(usuario)
    db.flush()
    return usuario


def _headers(usuario: Usuario, *permisos: str, roles: tuple[str, ...] = ()) -> dict[str, str]:
    token, _ = create_access_token(sub=str(usuario.id), roles=list(roles), perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def entorno(db_session, monkeypatch):
    """Dos proveedores; A: producto `a` (stock 20, mínimo 30) y `b` (stock 500, mínimo 10);
    B: producto `c` (sin inventario, mínimo 5); `d` sin proveedor."""
    db = db_session
    sufijo = uuid.uuid4().hex[:6]
    prov_a = Proveedor(nombre="Proveedor A", nit=f"A{sufijo}", lead_time_dias=3)
    prov_b = Proveedor(nombre="Proveedor B", nit=f"B{sufijo}", lead_time_dias=7)
    categoria = Categoria(nombre=f"cat-{sufijo}")
    db.add_all([prov_a, prov_b, categoria])
    db.flush()

    def producto(sku: str, proveedor: Proveedor | None, minimo: str, costo: str) -> Producto:
        return Producto(
            sku=f"{sku}-{sufijo}",
            nombre=f"Producto {sku}",
            categoria_id=categoria.id,
            proveedor_id=proveedor.id if proveedor else None,
            stock_minimo=Decimal(minimo),
            costo_unitario=Decimal(costo),
        )

    a = producto("A", prov_a, "30", "2.50")
    b = producto("B", prov_a, "10", "4.00")
    c = producto("C", prov_b, "5", "1.00")
    d = producto("D", None, "5", "1.00")
    db.add_all([a, b, c, d])
    db.flush()
    db.add_all(
        [
            Inventario(producto_id=a.id, stock_actual=Decimal("20")),
            Inventario(producto_id=b.id, stock_actual=Decimal("500")),
        ]
    )
    db.commit()

    demandas = {a.id: Decimal("70"), b.id: Decimal("100"), c.id: Decimal("12.5")}
    solicitudes: list = []

    def predecir_falso(_db, solicitud):
        solicitudes.append(solicitud)
        return DemandResponse(
            modelo=DemandModelInfo(id=uuid.uuid4(), algoritmo="xgboost", version="v1"),
            generado_en=datetime.now(UTC),
            pronosticos=[
                DemandProductForecast(
                    producto_id=pid,
                    serie=[
                        DemandPoint(
                            fecha_objetivo=solicitud.fecha_base + timedelta(days=i + 1),
                            demanda_predicha=float(demandas[pid]) / solicitud.horizonte_dias,
                        )
                        for i in range(solicitud.horizonte_dias)
                    ],
                )
                for pid in solicitud.producto_ids
                if pid in demandas
            ],
        )

    monkeypatch.setattr(purchasing_service.prediction_service, "predecir_demanda", predecir_falso)
    app.dependency_overrides[get_db] = lambda: db
    compras = _usuario(db, "compras")
    bodega = _usuario(db, "bodega")
    usuario_a = _usuario(db, "usuario-prov-a", prov_a)
    usuario_b = _usuario(db, "usuario-prov-b", prov_b)
    try:
        yield SimpleNamespace(
            db=db,
            client=TestClient(app),
            prov_a=prov_a,
            prov_b=prov_b,
            a=a,
            b=b,
            c=c,
            d=d,
            solicitudes=solicitudes,
            compras=_headers(compras, *COMPRAS, roles=("EncargadoCompras",)),
            bodega=_headers(bodega, *BODEGA, roles=("EncargadoBodega",)),
            bodega_id=bodega.id,
            proveedor_a=_headers(usuario_a, *PROVEEDOR, roles=("Proveedor",)),
            proveedor_b=_headers(usuario_b, *PROVEEDOR, roles=("Proveedor",)),
        )
    finally:
        app.dependency_overrides.clear()


def _crear(e, items=None, **extra):
    items = items or [
        {"producto_id": str(e.a.id), "cantidad": "80"},
        {"producto_id": str(e.b.id), "cantidad": "10.5", "costo_unitario": "5.00"},
    ]
    cuerpo = {"proveedor_id": str(e.prov_a.id), "items": items, **extra}
    return e.client.post(f"{BASE}/orders", json=cuerpo, headers=e.compras)


def _accion(e, metodo: str, pedido_id, sufijo: str, headers, **cuerpo):
    return e.client.request(
        metodo, f"{BASE}/orders/{pedido_id}/{sufijo}", headers=headers, json=cuerpo or None
    )


def _kardex(e, producto: Producto) -> list[Kardex]:
    e.db.expire_all()
    return list(
        e.db.scalars(select(Kardex).where(Kardex.producto_id == producto.id).order_by(Kardex.id))
    )


def _stock(e, producto: Producto) -> Decimal | None:
    e.db.expire_all()
    inv = e.db.scalars(select(Inventario).where(Inventario.producto_id == producto.id)).first()
    return inv.stock_actual if inv else None


# ------------------------------------------------------------------ sugerencias
# TC-COMP-01
def test_formula_de_reabastecimiento():
    calc = purchasing_service.calcular_cantidad_a_pedir
    assert calc(Decimal("70"), Decimal("30"), Decimal("20")) == Decimal("80.00")
    assert calc(Decimal("10"), Decimal("5"), Decimal("500")) == Decimal("0.00")  # nunca negativa


# TC-COMP-01
def test_sugerencias_cruzan_demanda_stock_y_punto_de_reorden(entorno):
    e = entorno
    r = e.client.get(f"{BASE}/suggestions", params={"horizonte_dias": 5}, headers=e.compras)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["horizonte_dias"] == 5 and cuerpo["advertencias"] == []

    por_sku = {s["sku"]: s for s in cuerpo["sugerencias"]}
    # A: (70 + 30) - 20 = 80 ; C: (12.5 + 5) - 0 = 17.5 ; B (500 ≥ 110) y D (sin proveedor) no.
    assert set(por_sku) == {e.a.sku, e.c.sku}
    sa = por_sku[e.a.sku]
    assert sa["cantidad_sugerida"] == "80.00" and sa["demanda_proyectada"] == "70.00"
    assert (sa["proveedor_nombre"], sa["lead_time_dias"]) == ("Proveedor A", 3)
    assert sa["costo_unitario"] == "2.50" and sa["pronostico_disponible"] is True
    sc = por_sku[e.c.sku]  # producto sin fila de inventario: stock 0
    assert (sc["cantidad_sugerida"], sc["stock_actual"], sc["lead_time_dias"]) == (
        "17.50",
        "0.00",
        7,
    )
    assert all(s.horizonte_dias == 5 for s in e.solicitudes)
    assert e.d.id not in {p for s in e.solicitudes for p in s.producto_ids}


# TC-COMP-02
def test_sugerencias_sin_modelo_usan_punto_de_reorden(entorno, monkeypatch):
    def sin_modelo(_db, _solicitud):
        raise AppError("SIN_MODELO_PRODUCTIVO", "sin modelo")

    monkeypatch.setattr(purchasing_service.prediction_service, "predecir_demanda", sin_modelo)
    r = entorno.client.get(f"{BASE}/suggestions", headers=entorno.compras)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["advertencias"]
    por_sku = {s["sku"]: s for s in cuerpo["sugerencias"]}
    # Demanda 0: A = 30 - 20 = 10 ; C = 5 - 0 = 5.
    assert por_sku[entorno.a.sku]["cantidad_sugerida"] == "10.00"
    assert por_sku[entorno.c.sku]["pronostico_disponible"] is False


# TC-COMP-02
def test_sugerencias_omiten_productos_sin_historial(entorno, monkeypatch):
    original = purchasing_service.prediction_service.predecir_demanda

    def con_faltante(db, solicitud):
        if entorno.c.id in solicitud.producto_ids:
            raise AppError(
                "HISTORIAL_INSUFICIENTE",
                "sin historia",
                detalle={"producto_ids": [str(entorno.c.id)], "dias_minimos": 14},
            )
        return original(db, solicitud)

    monkeypatch.setattr(purchasing_service.prediction_service, "predecir_demanda", con_faltante)
    cuerpo = entorno.client.get(f"{BASE}/suggestions", headers=entorno.compras).json()
    por_sku = {s["sku"]: s for s in cuerpo["sugerencias"]}
    assert por_sku[entorno.a.sku]["cantidad_sugerida"] == "80.00"
    assert por_sku[entorno.c.sku]["pronostico_disponible"] is False
    assert por_sku[entorno.c.sku]["cantidad_sugerida"] == "5.00"
    assert cuerpo["advertencias"]


# ------------------------------------------------------------------ ciclo completo
# TC-COMP-03
def test_ciclo_completo_orden_recepcion_e_incremento_de_kardex(entorno):
    e = entorno
    r = _crear(e)
    assert r.status_code == 201, r.text
    pedido = r.json()
    assert pedido["estado"] == "borrador"
    # 80 × 2.50 (costo del catálogo) + 10.5 × 5.00 (costo explícito)
    assert pedido["total"] == "252.50"
    assert pedido["proveedor_nombre"] == "Proveedor A" and len(pedido["items"]) == 2
    pid = pedido["id"]

    # borrador → enviado (Compras)
    enviado = _accion(e, "POST", pid, "send", e.compras)
    assert (enviado.status_code, enviado.json()["estado"]) == (200, "enviado"), enviado.text

    # enviado → confirmado (Proveedor A, con fecha estimada)
    confirmado = _accion(
        e, "PATCH", pid, "confirm", e.proveedor_a, fecha_esperada=MANANA.isoformat()
    )
    assert confirmado.status_code == 200, confirmado.text
    assert confirmado.json()["estado"] == "confirmado"
    assert confirmado.json()["fecha_esperada"] == MANANA.isoformat()
    assert _kardex(e, e.a) == []  # aún no hay ingreso físico
    assert _stock(e, e.a) == 20

    # confirmado → recibido (Bodega): entrada en kardex + stock_actual
    recibido = _accion(e, "POST", pid, "receive", e.bodega)
    assert recibido.status_code == 200, recibido.text
    assert recibido.json()["estado"] == "recibido"

    assert _stock(e, e.a) == 100 and _stock(e, e.b) == Decimal("510.50")
    (entrada_a,) = _kardex(e, e.a)
    assert entrada_a.tipo_movimiento == TipoMovimiento.ENTRADA
    assert (entrada_a.cantidad, entrada_a.saldo_resultante) == (80, 100)
    assert (entrada_a.referencia_tipo, str(entrada_a.referencia_id)) == ("pedido", pid)
    assert entrada_a.usuario_id == e.bodega_id
    (entrada_b,) = _kardex(e, e.b)
    assert (entrada_b.cantidad, entrada_b.saldo_resultante) == (Decimal("10.50"), Decimal("510.50"))

    # el kardex es visible por la API de inventario
    r = e.client.get(
        "/api/v1/inventory/kardex", params={"producto_id": str(e.a.id)}, headers=e.bodega
    )
    assert [m["tipo_movimiento"] for m in r.json()["items"]] == ["entrada"]


# TC-COMP-04
def test_crear_con_enviar_nace_enviado_y_recepcion_crea_inventario_faltante(entorno):
    e = entorno
    r = e.client.post(
        f"{BASE}/orders",
        json={
            "proveedor_id": str(e.prov_b.id),
            "items": [{"producto_id": str(e.c.id), "cantidad": "20"}],
            "enviar": True,
        },
        headers=e.compras,
    )
    assert (r.status_code, r.json()["estado"]) == (201, "enviado"), r.text
    pid = r.json()["id"]
    assert _stock(e, e.c) is None  # C nunca tuvo fila de inventario

    _accion(e, "PATCH", pid, "confirm", e.proveedor_b, fecha_esperada=MANANA.isoformat())
    assert _accion(e, "POST", pid, "receive", e.bodega).status_code == 200
    assert _stock(e, e.c) == 20
    (entrada,) = _kardex(e, e.c)
    assert (entrada.tipo_movimiento, entrada.saldo_resultante) == (TipoMovimiento.ENTRADA, 20)


# TC-COMP-05
def test_transiciones_invalidas_y_recepcion_no_se_repite(entorno):
    e = entorno
    pid = _crear(e).json()["id"]

    for sufijo, metodo, headers, cuerpo in (
        ("confirm", "PATCH", e.proveedor_a, {"fecha_esperada": MANANA.isoformat()}),
        ("receive", "POST", e.bodega, {}),
    ):
        r = _accion(e, metodo, pid, sufijo, headers, **cuerpo)
        assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_PEDIDO_INVALIDO"), sufijo

    assert _accion(e, "POST", pid, "send", e.compras).status_code == 200
    r = _accion(e, "POST", pid, "send", e.compras)  # ya enviado
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_PEDIDO_INVALIDO")
    r = _accion(e, "POST", pid, "receive", e.bodega)  # enviado, no confirmado
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_PEDIDO_INVALIDO")

    _accion(e, "PATCH", pid, "confirm", e.proveedor_a, fecha_esperada=MANANA.isoformat())
    assert _accion(e, "POST", pid, "receive", e.bodega).status_code == 200
    r = _accion(e, "POST", pid, "receive", e.bodega)  # doble recepción
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_PEDIDO_INVALIDO")
    assert _stock(e, e.a) == 100 and len(_kardex(e, e.a)) == 1  # sin doble ingreso


# TC-COMP-05
def test_cancelar_pedido_y_no_recibirlo(entorno):
    e = entorno
    pid = _crear(e).json()["id"]
    r = _accion(e, "POST", pid, "cancel", e.compras)
    assert (r.status_code, r.json()["estado"]) == (200, "cancelado")
    r = _accion(e, "POST", pid, "cancel", e.compras)
    assert (r.status_code, r.json()["codigo"]) == (400, "ESTADO_PEDIDO_INVALIDO")


# TC-COMP-05
def test_confirmar_con_fecha_anterior_al_pedido_es_400(entorno):
    e = entorno
    pid = _crear(e, enviar=True).json()["id"]
    ayer = (date.today() - timedelta(days=1)).isoformat()
    r = _accion(e, "PATCH", pid, "confirm", e.proveedor_a, fecha_esperada=ayer)
    assert (r.status_code, r.json()["codigo"]) == (400, "FECHA_ESPERADA_INVALIDA")


# ------------------------------------------------------------------ validación de la orden
# TC-COMP-06
def test_producto_ajeno_al_proveedor_o_inexistente_es_400(entorno):
    e = entorno
    r = _crear(e, items=[{"producto_id": str(e.c.id), "cantidad": "5"}])  # C es de B
    assert (r.status_code, r.json()["codigo"]) == (400, "PRODUCTO_AJENO_A_PROVEEDOR")
    r = _crear(e, items=[{"producto_id": str(e.d.id), "cantidad": "5"}])  # sin proveedor
    assert (r.status_code, r.json()["codigo"]) == (400, "PRODUCTO_AJENO_A_PROVEEDOR")
    r = _crear(e, items=[{"producto_id": str(uuid.uuid4()), "cantidad": "5"}])
    assert (r.status_code, r.json()["codigo"]) == (400, "PRODUCTO_NO_ENCONTRADO")
    cuerpo = {
        "proveedor_id": str(uuid.uuid4()),
        "items": [{"producto_id": str(e.a.id), "cantidad": 1}],
    }
    r = e.client.post(f"{BASE}/orders", json=cuerpo, headers=e.compras)
    assert (r.status_code, r.json()["codigo"]) == (400, "PROVEEDOR_NO_ENCONTRADO")


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"items": []},
        {"items": [{"producto_id": "x", "cantidad": 1}]},
        {"items": [{"producto_id": str(uuid.uuid4()), "cantidad": 0}]},
        {"items": [{"producto_id": str(uuid.uuid4()), "cantidad": -3}]},
    ],
)
# TC-COMP-06
def test_cuerpo_invalido_es_422(entorno, cuerpo):
    r = entorno.client.post(
        f"{BASE}/orders",
        json={"proveedor_id": str(entorno.prov_a.id), **cuerpo},
        headers=entorno.compras,
    )
    assert r.status_code == 422


# TC-COMP-06
def test_items_repetidos_es_422(entorno):
    item = {"producto_id": str(entorno.a.id), "cantidad": 1}
    assert _crear(entorno, items=[item, item]).status_code == 422


# ------------------------------------------------------------------ RBAC y aislamiento
def test_tc_rbac_03_proveedor_no_accede_a_pedidos_de_otro_proveedor(entorno):
    e = entorno
    pid = _crear(e, enviar=True).json()["id"]  # pedido del Proveedor A

    r = _accion(e, "PATCH", pid, "confirm", e.proveedor_b, fecha_esperada=MANANA.isoformat())
    assert (r.status_code, r.json()["codigo"]) == (404, "PEDIDO_NO_ENCONTRADO")
    assert e.client.get(f"{BASE}/orders/{pid}", headers=e.proveedor_b).status_code == 404
    listado = e.client.get(f"{BASE}/orders", headers=e.proveedor_b).json()
    assert listado["items"] == [] and listado["total"] == 0
    # el pedido sigue enviado y el dueño sí lo ve y lo confirma
    assert e.client.get(f"{BASE}/orders/{pid}", headers=e.proveedor_a).json()["estado"] == "enviado"
    assert e.client.get(f"{BASE}/orders", headers=e.proveedor_a).json()["total"] == 1
    r = _accion(e, "PATCH", pid, "confirm", e.proveedor_a, fecha_esperada=MANANA.isoformat())
    assert r.status_code == 200


# TC-COMP-07
def test_compras_ve_todos_los_pedidos_y_filtra_por_estado(entorno):
    e = entorno
    _crear(e)
    _crear(e, enviar=True)
    e.client.post(
        f"{BASE}/orders",
        json={
            "proveedor_id": str(e.prov_b.id),
            "items": [{"producto_id": str(e.c.id), "cantidad": 1}],
        },
        headers=e.compras,
    )
    todos = e.client.get(f"{BASE}/orders", headers=e.compras).json()
    assert todos["total"] == 3
    enviados = e.client.get(f"{BASE}/orders", params={"estado": "enviado"}, headers=e.compras)
    assert [p["estado"] for p in enviados.json()["items"]] == ["enviado"]


# TC-COMP-07
def test_matriz_de_permisos_de_compras(entorno):
    e = entorno
    pid = _crear(e, enviar=True).json()["id"]
    cuerpo = {
        "proveedor_id": str(e.prov_a.id),
        "items": [{"producto_id": str(e.a.id), "cantidad": 1}],
    }
    fecha = {"fecha_esperada": MANANA.isoformat()}

    # Bodega y Proveedor no gestionan; Compras no confirma ni recibe.
    for headers in (e.bodega, e.proveedor_a):
        assert e.client.post(f"{BASE}/orders", json=cuerpo, headers=headers).status_code == 403
        assert e.client.get(f"{BASE}/suggestions", headers=headers).status_code == 403
        assert _accion(e, "POST", pid, "send", headers).status_code == 403
        assert _accion(e, "POST", pid, "cancel", headers).status_code == 403
    # Bodega sí consulta los pedidos (necesita verlos para recibirlos), pero no los gestiona.
    assert e.client.get(f"{BASE}/orders", headers=e.bodega).status_code == 200
    assert e.client.get(f"{BASE}/orders/{pid}", headers=e.bodega).status_code == 200
    assert _accion(e, "PATCH", pid, "confirm", e.compras, **fecha).status_code == 403
    assert _accion(e, "PATCH", pid, "confirm", e.bodega, **fecha).status_code == 403
    assert _accion(e, "POST", pid, "receive", e.compras).status_code == 403
    assert _accion(e, "POST", pid, "receive", e.proveedor_a).status_code == 403

    # Sin token: 401.
    assert e.client.get(f"{BASE}/orders").status_code == 401
    assert e.client.post(f"{BASE}/orders", json=cuerpo).status_code == 401
    assert e.client.post(f"{BASE}/orders/{pid}/receive").status_code == 401


# TC-COMP-07
def test_usuario_con_permiso_de_confirmar_sin_proveedor_asociado_es_403(entorno):
    e = entorno
    pid = _crear(e, enviar=True).json()["id"]
    suelto = _usuario(e.db, "suelto")
    headers = _headers(suelto, *PROVEEDOR, roles=("Proveedor",))
    r = _accion(e, "PATCH", pid, "confirm", headers, fecha_esperada=MANANA.isoformat())
    assert (r.status_code, r.json()["codigo"]) == (403, "PROVEEDOR_NO_ASOCIADO")
    assert e.client.get(f"{BASE}/orders", headers=headers).status_code == 403


# TC-COMP-07
def test_pedido_inexistente_es_404(entorno):
    e = entorno
    fantasma = uuid.uuid4()
    assert e.client.get(f"{BASE}/orders/{fantasma}", headers=e.compras).status_code == 404
    assert _accion(e, "POST", fantasma, "send", e.compras).status_code == 404
    assert _accion(e, "POST", fantasma, "receive", e.bodega).status_code == 404
