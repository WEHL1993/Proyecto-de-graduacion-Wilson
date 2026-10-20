"""Recepciones documentadas contra PostgreSQL aislado."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.domain.models.operations import RecepcionMercaderia
from app.services import inventory_service
from tests.integration import test_purchasing as compras_tests
from tests.integration.test_purchasing import (
    BASE,
    MANANA,
    _accion,
    _crear,
    _kardex,
    _stock,
)

db_session = compras_tests.db_session
entorno = compras_tests.entorno


@pytest.fixture(autouse=True)
def _solo_bd_aislada():
    from sqlalchemy.engine import make_url

    assert make_url(get_settings().sqlalchemy_database_uri).port == 55432, (
        "Las pruebas de recepción requieren DATABASE_URL con puerto 55432."
    )


def solicitud(e, pedido_id=None, cantidades=("80", "10.5")):
    return {
        "pedido_id": pedido_id,
        "serie": " 1fef6cc7 ",
        "numero": "1265782595",
        "numero_autorizacion": "1FEF6CC7-4B72-4F43-A218-C10D0D12CE48",
        "fecha_emision": "2026-10-20",
        "condicion_pago": "Crédito a 3 días",
        "serie_admin": "FEL14",
        "numero_admin": "77058",
        "items": [
            {"producto_id": str(p.id), "cantidad_recibida": q, "observacion": "Caja revisada"}
            for p, q in zip((e.a, e.b), cantidades, strict=True)
        ],
    }


def confirmado(e):
    pedido = _crear(e, enviar=True).json()["id"]
    r = _accion(e, "PATCH", pedido, "confirm", e.proveedor_a, fecha_esperada=str(MANANA))
    assert r.status_code == 200
    return pedido


@pytest.mark.parametrize(
    "cantidades,estado",
    [
        (("80", "10.5"), "recibido"),
        (("70", "0"), "recibido_parcial"),
        (("81", "11"), "recibido_parcial"),
    ],
)
def test_recepcion_actualiza_stock_documento_y_estado(entorno, cantidades, estado):
    e = entorno
    pedido = confirmado(e)
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=solicitud(e, pedido, cantidades))
    assert r.status_code == 201, r.text
    assert r.json()["estado_pedido"] == estado
    assert _stock(e, e.a) == Decimal("20") + Decimal(cantidades[0])
    assert _stock(e, e.b) == Decimal("500") + Decimal(cantidades[1])
    movimientos = _kardex(e, e.a)
    assert len(movimientos) == 1
    assert movimientos[0].referencia_tipo == "recepcion"
    assert str(movimientos[0].referencia_id) == r.json()["id"]
    assert movimientos[0].motivo == "FEL 1FEF6CC7-1265782595 / 1fef6cc7-4b72-4f43-a218-c10d0d12ce48"
    assert len(_kardex(e, e.b)) == (1 if Decimal(cantidades[1]) > 0 else 0)
    doc = e.db.get(RecepcionMercaderia, uuid.UUID(r.json()["id"]))
    assert doc.items[1]["observacion"] == "Caja revisada"
    assert doc.serie == "1FEF6CC7"
    assert doc.condicion_pago == "Crédito a 3 días"
    assert (doc.serie_admin, doc.numero_admin) == ("FEL14", "77058")
    assert r.json()["fecha_emision"] == "2026-10-20"
    assert r.json()["numero_autorizacion"] == str(doc.numero_autorizacion)
    assert (
        e.client.post(f"{BASE}/receipts", headers=e.bodega, json=solicitud(e, pedido)).status_code
        == 409
    )
    assert _stock(e, e.a) == Decimal("20") + Decimal(cantidades[0])


def test_sin_pedido_y_permiso_de_catalogo(entorno):
    e = entorno
    assert e.client.get(f"{BASE}/receipt-products", headers=e.bodega).status_code == 200
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=solicitud(e))
    assert r.status_code == 201, r.text
    assert r.json()["estado_pedido"] is None
    assert _stock(e, e.a) == Decimal("100")


@pytest.mark.parametrize(
    "caso",
    ["documento", "duplicado", "negativo", "precision", "cero", "ajeno", "inactivo", "faltante"],
)
def test_rechazos_no_mutan_stock(entorno, caso):
    e = entorno
    pedido = confirmado(e)
    body = solicitud(e, pedido)
    if caso == "documento":
        body["serie"] = "   "
    if caso == "duplicado":
        body["items"][1] = body["items"][0]
    if caso == "negativo":
        body["items"][0]["cantidad_recibida"] = "-1"
    if caso == "precision":
        body["items"][0]["cantidad_recibida"] = "1.001"
    if caso == "cero":
        for i in body["items"]:
            i["cantidad_recibida"] = "0"
    if caso == "ajeno":
        body["items"][1]["producto_id"] = str(e.c.id)
    if caso == "inactivo":
        e.a.activo = False
        e.db.flush()
    if caso == "faltante":
        body["items"].pop()
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=body)
    assert r.status_code in (400, 422), r.text
    assert _stock(e, e.a) == Decimal("20")
    assert not _kardex(e, e.a)


def test_permiso_obligatorio(entorno):
    e = entorno
    assert (
        e.client.post(f"{BASE}/receipts", headers=e.compras, json=solicitud(e)).status_code == 403
    )
    assert e.client.post(f"{BASE}/receipts", json=solicitud(e)).status_code == 401


def test_fallo_de_inventario_revierte_documento_y_entradas(entorno, monkeypatch):
    e = entorno
    pedido = confirmado(e)
    original = inventory_service.registrar_entrada

    def fallar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Fallo simulado antes del commit")

    monkeypatch.setattr(inventory_service, "registrar_entrada", fallar)
    with pytest.raises(RuntimeError):
        e.client.post(f"{BASE}/receipts", headers=e.bodega, json=solicitud(e, pedido))
    # La dependencia de produccion cierra y revierte la sesion ante errores no controlados.
    e.db.rollback()
    assert _stock(e, e.a) == Decimal("20")
    assert not _kardex(e, e.a)
    assert e.db.scalar(select(func.count()).select_from(RecepcionMercaderia)) == 0


@pytest.mark.parametrize("clave", ["numero_autorizacion", "serie_numero"])
def test_factura_duplicada_es_409_y_no_duplica_stock(entorno, clave):
    e = entorno
    original = solicitud(e)
    assert e.client.post(f"{BASE}/receipts", headers=e.bodega, json=original).status_code == 201
    repetida = solicitud(e)
    if clave == "numero_autorizacion":
        repetida["numero"] = "999"
        repetida["numero_autorizacion"] = original["numero_autorizacion"].lower()
    else:
        repetida["numero_autorizacion"] = str(uuid.uuid4())
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=repetida)
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == "FACTURA_DUPLICADA"
    assert "La factura ya fue registrada" in r.json()["mensaje"]
    assert _stock(e, e.a) == Decimal("100")
    assert len(_kardex(e, e.a)) == 1
    assert e.db.scalar(select(func.count()).select_from(RecepcionMercaderia)) == 1


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("serie", None),
        ("numero", None),
        ("numero_autorizacion", None),
        ("fecha_emision", None),
        ("numero", "ABC"),
        ("numero_autorizacion", "no-es-uuid"),
        ("fecha_emision", "2026-02-30"),
    ],
)
def test_encabezado_fel_invalido_no_muta_stock(entorno, campo, valor):
    e = entorno
    body = solicitud(e)
    if valor is None:
        body.pop(campo)
    else:
        body[campo] = valor
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=body)
    assert r.status_code == 422, r.text
    assert _stock(e, e.a) == Decimal("20")
    assert not _kardex(e, e.a)


def test_encabezado_fel_sin_opcionales(entorno):
    e = entorno
    body = solicitud(e)
    for campo in ("condicion_pago", "serie_admin", "numero_admin"):
        body.pop(campo)
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=body)
    assert r.status_code == 201, r.text
    assert all(
        r.json()[campo] is None for campo in ("condicion_pago", "serie_admin", "numero_admin")
    )


@pytest.mark.parametrize("clave", ["numero_autorizacion", "serie_numero"])
def test_unique_en_bd_traduce_conflicto_a_409(entorno, monkeypatch, clave):
    """Omite solo la consulta previa para verificar la garantía UNIQUE ante carreras."""
    e = entorno
    assert e.client.post(f"{BASE}/receipts", headers=e.bodega, json=solicitud(e)).status_code == 201
    original_scalar = e.db.scalar

    def sin_preconsulta(statement, *args, **kwargs):
        if str(statement).startswith("SELECT recepciones_mercaderia.id"):
            return None
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(e.db, "scalar", sin_preconsulta)
    body = solicitud(e)
    if clave == "numero_autorizacion":
        body["numero"] = "999"
    else:
        body["numero_autorizacion"] = str(uuid.uuid4())
    r = e.client.post(f"{BASE}/receipts", headers=e.bodega, json=body)
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == "FACTURA_DUPLICADA"
    assert _stock(e, e.a) == Decimal("100")
    assert len(_kardex(e, e.a)) == 1
