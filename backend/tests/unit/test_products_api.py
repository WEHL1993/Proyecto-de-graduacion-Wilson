"""Productos con baja lógica y ajuste de stock (ADR-16) sin BD: guardas RBAC, DTOs y seed.

La sesión se sustituye por un doble y los servicios por stubs: solo se verifica que el router
exija el permiso correcto, valide las entradas y delegue con el código HTTP esperado.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database import get_db
from app.core.security import create_access_token
from app.db.seeds.seed_rbac import MATRIZ_ROL_PERMISO, PERMISOS
from app.main import app
from app.schemas.inventory import AjusteRequest
from app.schemas.products import ProductoCreate, ProductoUpdate
from app.services import inventory_service, product_service

PID = uuid.uuid4()
PRODUCTOS = "/api/v1/products"
AJUSTES = "/api/v1/inventory/adjustments"
CUERPO_PRODUCTO = {"sku": "ABC", "nombre": "Producto", "categoria_id": str(uuid.uuid4())}
CUERPO_AJUSTE = {
    "producto_id": str(PID),
    "tipo": "incremento",
    "cantidad": "5",
    "motivo": "Conteo físico de bodega",
}

# (método, ruta, cuerpo, permiso requerido, código de éxito)
RUTAS = [
    ("GET", PRODUCTOS, None, "inventario:leer", 200),
    ("GET", f"{PRODUCTOS}/{PID}", None, "inventario:leer", 200),
    ("POST", PRODUCTOS, CUERPO_PRODUCTO, "productos:crear", 201),
    ("PATCH", f"{PRODUCTOS}/{PID}", {"nombre": "Otro"}, "productos:editar", 200),
    ("DELETE", f"{PRODUCTOS}/{PID}", None, "productos:eliminar", 204),
    ("POST", f"{PRODUCTOS}/{PID}/reactivate", None, "productos:eliminar", 200),
    ("POST", AJUSTES, CUERPO_AJUSTE, "inventario:ajustar", 201),
]


def _headers(*permisos: str) -> dict[str, str]:
    token, _ = create_access_token(sub=str(uuid.uuid4()), roles=[], perms=list(permisos))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cliente(monkeypatch):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    for nombre in ("listar", "obtener", "crear", "actualizar", "reactivar"):
        monkeypatch.setattr(product_service, nombre, lambda *a, **k: _Salida())
    monkeypatch.setattr(product_service, "dar_de_baja", lambda *a, **k: None)
    monkeypatch.setattr(inventory_service, "ajustar_existencias", lambda *a, **k: _Salida())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


class _Salida:
    """Respuesta mínima que FastAPI no puede validar: solo interesa el flujo hasta el servicio."""


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso", "_ok"), RUTAS)
# TC-PROD-07 (capa HTTP)
def test_sin_token_responde_401(cliente, metodo, ruta, cuerpo, permiso, _ok):
    r = cliente.request(metodo, ruta, json=cuerpo)
    assert r.status_code == 401 and r.json()["codigo"] == "NO_AUTENTICADO"


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso", "_ok"), RUTAS)
def test_sin_el_permiso_responde_403(cliente, metodo, ruta, cuerpo, permiso, _ok):
    otros = [p for p in PERMISOS if p != permiso]
    r = cliente.request(metodo, ruta, json=cuerpo, headers=_headers(*otros))
    assert r.status_code == 403 and r.json()["codigo"] == "PERMISO_DENEGADO"
    assert permiso in r.json()["mensaje"]


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permiso", "codigo_ok"), RUTAS)
def test_con_el_permiso_pasa_la_guarda(cliente, metodo, ruta, cuerpo, permiso, codigo_ok):
    r = cliente.request(metodo, ruta, json=cuerpo, headers=_headers(permiso))
    assert r.status_code not in (401, 403, 404, 422)
    if metodo == "DELETE":
        assert r.status_code == 204


@pytest.mark.parametrize(
    "cuerpo",
    [
        {**CUERPO_PRODUCTO, "precio_venta": "-1"},
        {**CUERPO_PRODUCTO, "stock_minimo": "-0.01"},
        {**CUERPO_PRODUCTO, "sku": ""},
        {**CUERPO_PRODUCTO, "categoria_id": "no-es-uuid"},
        {"sku": "X"},
    ],
)
def test_crear_valida_el_cuerpo(cliente, cuerpo):
    r = cliente.post(PRODUCTOS, json=cuerpo, headers=_headers("productos:crear"))
    assert r.status_code == 422


@pytest.mark.parametrize(
    "cambio",
    [
        {"motivo": "abc"},  # menos de 5 caracteres
        {"motivo": "x" * 301},
        {"cantidad": "-1"},
        {"tipo": "multiplicar"},
        {"producto_id": "no-es-uuid"},
    ],
)
def test_ajuste_valida_el_cuerpo(cliente, cambio):
    r = cliente.post(
        AJUSTES, json={**CUERPO_AJUSTE, **cambio}, headers=_headers("inventario:ajustar")
    )
    assert r.status_code == 422


def test_dtos_aceptan_valores_validos_y_rechazan_negativos():
    p = ProductoCreate(sku="a", nombre="Gaseosa", categoria_id=uuid.uuid4())
    assert p.precio_venta == Decimal("0") and p.unidad_medida == "unidad"
    assert ProductoUpdate().model_fields_set == set()
    assert ProductoUpdate(proveedor_id=None).model_fields_set == {"proveedor_id"}
    with pytest.raises(ValidationError):
        ProductoCreate(sku="a", nombre="Gaseosa", categoria_id=uuid.uuid4(), costo_unitario=-1)
    ajuste = AjusteRequest(producto_id=PID, tipo="fijar", cantidad=0, motivo="Conteo en cero")
    assert ajuste.cantidad == 0


def test_listado_de_productos_usa_activos_por_defecto(monkeypatch):
    capturado: dict = {}

    def falso(db, **filtros):
        capturado.update(filtros)
        return _Salida()

    monkeypatch.setattr(product_service, "listar", falso)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        TestClient(app, raise_server_exceptions=False).get(
            PRODUCTOS, headers=_headers("inventario:leer")
        )
        assert capturado["activo"] is True
        TestClient(app, raise_server_exceptions=False).get(
            PRODUCTOS, params={"activo": "false"}, headers=_headers("inventario:leer")
        )
        assert capturado["activo"] is False
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ seed de RBAC
def test_seed_define_los_permisos_nuevos_y_su_matriz():
    nuevos = {"productos:crear", "productos:editar", "productos:eliminar"}
    assert nuevos <= PERMISOS.keys()
    assert nuevos <= set(MATRIZ_ROL_PERMISO["Admin"])
    assert nuevos <= set(MATRIZ_ROL_PERMISO["Inventario"])
    for rol in ("Bodega", "Ventas", "Compras", "Gerente", "Proveedor"):
        assert not nuevos & set(MATRIZ_ROL_PERMISO[rol]), rol
    # El ajuste de stock ya existía y sigue en Admin, Inventario y Bodega.
    for rol in ("Admin", "Inventario", "Bodega"):
        assert "inventario:ajustar" in MATRIZ_ROL_PERMISO[rol]
