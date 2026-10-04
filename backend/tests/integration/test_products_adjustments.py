"""CRUD de productos con baja lógica y ajuste manual de stock contra PostgreSQL real (ADR-16).

Requiere la BD migrada; se omiten si no hay conexión. Cada prueba corre en una transacción que
se revierte al final, salvo la de concurrencia, que usa sesiones reales y limpia sus datos.
La bitácora (append-only) está apagada por el `conftest` global, así que no deja rastro.
"""

import threading
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.core.database import get_sessionmaker
from app.core.errors import AppError
from app.domain.enums import EstadoAlerta, TipoAlerta
from app.domain.models.auth import Usuario
from app.domain.models.catalog import Categoria, Inventario, Kardex, Producto, Proveedor, Ruta
from app.domain.models.ml import Alerta, ModeloML
from app.domain.models.operations import CargaRuta, DetalleCarga
from app.domain.models.sales import EtlLote, VentaHistorica
from app.repositories import sales_repo
from app.schemas.inventory import AjusteRequest
from app.services import inventory_service, prediction_service

from .conftest import crear_usuario, encabezados

PRODUCTOS = "/api/v1/products"
INVENTARIO = "/api/v1/inventory"
ADMIN = (
    "inventario:leer",
    "inventario:ajustar",
    "productos:crear",
    "productos:editar",
    "productos:eliminar",
)


@pytest.fixture
def entorno(db_tx, cliente):
    db = db_tx
    sufijo = uuid.uuid4().hex[:6]
    categoria = Categoria(nombre=f"cat-{sufijo}")
    proveedor = Proveedor(nombre="Proveedor X", nit=f"N{sufijo}", lead_time_dias=2)
    usuario = crear_usuario(db, "admin-productos")
    db.add_all([categoria, proveedor])
    db.commit()
    return SimpleNamespace(
        db=db,
        client=cliente,
        categoria=categoria,
        proveedor=proveedor,
        usuario=usuario,
        sufijo=sufijo,
        h=encabezados(usuario, *ADMIN, roles=("Admin",)),
    )


def _nuevo(e, **extra) -> dict:
    return {
        "sku": f"sku-{uuid.uuid4().hex[:8]}",
        "nombre": "Producto de prueba",
        "categoria_id": str(e.categoria.id),
        "precio_venta": "12.50",
        "costo_unitario": "8.00",
        "stock_minimo": "10",
        **extra,
    }


def _crear(e, **extra) -> dict:
    r = e.client.post(PRODUCTOS, json=_nuevo(e, **extra), headers=e.h)
    assert r.status_code == 201, r.text
    return r.json()


def _ajustar(e, producto_id, tipo, cantidad, motivo="Conteo físico de bodega", headers=None):
    return e.client.post(
        f"{INVENTARIO}/adjustments",
        json={
            "producto_id": str(producto_id),
            "tipo": tipo,
            "cantidad": str(cantidad),
            "motivo": motivo,
        },
        headers=headers or e.h,
    )


# ------------------------------------------------------------------ RBAC
# TC-PROD-07
def test_exige_autenticacion_y_permisos(entorno):
    e = entorno
    p = _crear(e)
    assert e.client.get(PRODUCTOS).status_code == 401
    assert e.client.post(f"{INVENTARIO}/adjustments", json={}).status_code == 401

    solo_leer = encabezados(crear_usuario(e.db, "lector"), "inventario:leer")
    assert e.client.get(PRODUCTOS, headers=solo_leer).status_code == 200
    assert e.client.post(PRODUCTOS, json=_nuevo(e), headers=solo_leer).status_code == 403
    assert e.client.patch(f"{PRODUCTOS}/{p['id']}", json={}, headers=solo_leer).status_code == 403
    assert e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=solo_leer).status_code == 403
    assert e.client.post(f"{PRODUCTOS}/{p['id']}/reactivate", headers=solo_leer).status_code == 403
    assert _ajustar(e, p["id"], "incremento", 1, headers=solo_leer).status_code == 403

    sin_permisos = encabezados(crear_usuario(e.db, "sin-permisos"), "alertas:leer")
    assert e.client.get(PRODUCTOS, headers=sin_permisos).status_code == 403


# ------------------------------------------------------------------ alta
# TC-PROD-01
def test_crear_producto_normaliza_sku_y_crea_existencia_en_cero(entorno):
    e = entorno
    p = _crear(e, sku="  abc-1  ", proveedor_id=str(e.proveedor.id))
    assert p["sku"] == "ABC-1" and p["activo"] is True
    assert p["categoria"] == e.categoria.nombre and p["proveedor_id"] == str(e.proveedor.id)
    assert Decimal(p["stock_actual"]) == 0 and Decimal(p["stock_disponible"]) == 0

    inv = e.db.scalar(select(Inventario).where(Inventario.producto_id == uuid.UUID(p["id"])))
    assert inv is not None and inv.stock_actual == 0

    existencias = e.client.get(INVENTARIO, params={"producto_id": p["id"]}, headers=e.h).json()
    assert existencias["items"][0]["sku"] == "ABC-1"


# TC-PROD-01
def test_crear_rechaza_sku_duplicado_sin_distinguir_mayusculas(entorno):
    e = entorno
    _crear(e, sku="DUP-1")
    r = e.client.post(PRODUCTOS, json=_nuevo(e, sku="dup-1"), headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "SKU_DUPLICADO"


# TC-PROD-01
def test_crear_valida_categoria_proveedor_y_valores(entorno):
    e = entorno
    r = e.client.post(PRODUCTOS, json=_nuevo(e, categoria_id=str(uuid.uuid4())), headers=e.h)
    assert r.status_code == 404 and r.json()["codigo"] == "CATEGORIA_NO_ENCONTRADA"
    r = e.client.post(PRODUCTOS, json=_nuevo(e, proveedor_id=str(uuid.uuid4())), headers=e.h)
    assert r.status_code == 404 and r.json()["codigo"] == "PROVEEDOR_NO_ENCONTRADO"
    assert e.client.post(PRODUCTOS, json=_nuevo(e, precio_venta="-1"), headers=e.h).status_code in (
        400,
        422,
    )
    assert e.client.post(PRODUCTOS, json=_nuevo(e, sku="   "), headers=e.h).status_code in (
        400,
        422,
    )


# ------------------------------------------------------------------ edición
# TC-PROD-02
def test_editar_parcialmente_sin_tocar_existencias(entorno):
    e = entorno
    p = _crear(e, proveedor_id=str(e.proveedor.id))
    assert _ajustar(e, p["id"], "incremento", 40).status_code == 201

    r = e.client.patch(
        f"{PRODUCTOS}/{p['id']}",
        json={"nombre": "  Nombre nuevo ", "precio_venta": "20.00", "proveedor_id": None},
        headers=e.h,
    )
    assert r.status_code == 200, r.text
    editado = r.json()
    assert editado["nombre"] == "Nombre nuevo" and Decimal(editado["precio_venta"]) == 20
    assert editado["proveedor_id"] is None  # None explícito quita el proveedor
    assert Decimal(editado["costo_unitario"]) == 8  # lo no enviado no cambia
    assert Decimal(editado["stock_actual"]) == 40


# TC-PROD-02
def test_editar_rechaza_sku_duplicado_y_acepta_el_propio(entorno):
    e = entorno
    a = _crear(e, sku="EDIT-A")
    _crear(e, sku="EDIT-B")
    r = e.client.patch(f"{PRODUCTOS}/{a['id']}", json={"sku": "edit-b"}, headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "SKU_DUPLICADO"
    r = e.client.patch(f"{PRODUCTOS}/{a['id']}", json={"sku": "edit-a"}, headers=e.h)
    assert r.status_code == 200 and r.json()["sku"] == "EDIT-A"
    r = e.client.patch(f"{PRODUCTOS}/{uuid.uuid4()}", json={"nombre": "xx"}, headers=e.h)
    assert r.status_code == 404 and r.json()["codigo"] == "PRODUCTO_NO_ENCONTRADO"


# ------------------------------------------------------------------ baja lógica
# TC-PROD-03
def test_baja_logica_conserva_historial_y_es_idempotente(entorno):
    e = entorno
    p = _crear(e)
    assert _ajustar(e, p["id"], "incremento", 5).status_code == 201

    assert e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h).status_code == 204
    assert e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h).status_code == 204

    # La fila sigue existiendo (baja lógica) y su kardex es consultable.
    fila = e.db.get(Producto, uuid.UUID(p["id"]))
    assert fila is not None and fila.activo is False
    detalle = e.client.get(f"{PRODUCTOS}/{p['id']}", headers=e.h)
    assert detalle.status_code == 200 and detalle.json()["activo"] is False
    kardex = e.client.get(INVENTARIO + "/kardex", params={"producto_id": p["id"]}, headers=e.h)
    assert kardex.json()["total"] == 1

    ids_activos = {x["id"] for x in e.client.get(PRODUCTOS, headers=e.h).json()["items"]}
    assert p["id"] not in ids_activos
    bajas = e.client.get(PRODUCTOS, params={"activo": False, "q": p["sku"]}, headers=e.h)
    assert [x["id"] for x in bajas.json()["items"]] == [p["id"]]
    assert e.client.delete(f"{PRODUCTOS}/{uuid.uuid4()}", headers=e.h).status_code == 404


# TC-PROD-04
def test_baja_bloqueada_por_stock_reservado(entorno):
    e = entorno
    p = _crear(e)
    assert _ajustar(e, p["id"], "incremento", 20).status_code == 201
    inv = e.db.scalar(select(Inventario).where(Inventario.producto_id == uuid.UUID(p["id"])))
    inv.stock_reservado = Decimal("5")
    e.db.commit()

    r = e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "PRODUCTO_EN_USO"
    assert Decimal(r.json()["detalle"]["stock_reservado"]) == 5
    assert e.db.get(Producto, uuid.UUID(p["id"])).activo is True


# TC-PROD-04
def test_baja_bloqueada_por_carga_vigente_y_permitida_si_ya_despachada(entorno):
    e = entorno
    db = e.db
    p = _crear(e)
    ruta = Ruta(codigo=f"R-{e.sufijo}", nombre="Ruta prueba")
    modelo = ModeloML(
        nombre=f"demanda-{e.sufijo}",
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
    db.add_all([ruta, modelo])
    db.flush()
    carga = CargaRuta(
        ruta_id=ruta.id,
        fecha_operacion=date(2025, 4, 1),
        estado="borrador",
        modelo_id=modelo.id,
        generado_por=e.usuario.id,
    )
    carga.detalles = [
        DetalleCarga(
            producto_id=uuid.UUID(p["id"]),
            cantidad_predicha=Decimal("0"),
            stock_disponible_al_generar=Decimal("0"),
            cantidad_sugerida=Decimal("0"),
        )
    ]
    db.add(carga)
    db.commit()

    r = e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h)
    assert r.status_code == 409 and r.json()["codigo"] == "PRODUCTO_EN_USO"
    assert r.json()["detalle"]["cargas_vigentes"] == [str(carga.id)]

    carga.estado = "rechazada"  # una carga cerrada ya no bloquea
    db.commit()
    assert e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h).status_code == 204


# TC-PROD-05
def test_reactivar_producto(entorno):
    e = entorno
    p = _crear(e)
    e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h)
    r = e.client.post(f"{PRODUCTOS}/{p['id']}/reactivate", headers=e.h)
    assert r.status_code == 200 and r.json()["activo"] is True
    assert e.client.post(f"{PRODUCTOS}/{p['id']}/reactivate", headers=e.h).status_code == 200
    assert e.client.post(f"{PRODUCTOS}/{uuid.uuid4()}/reactivate", headers=e.h).status_code == 404


# ------------------------------------------------------------------ ajuste de stock
# TC-AJU-01
def test_ajustes_incremento_decremento_y_fijar_dejan_kardex_firmado(entorno):
    e = entorno
    p = _crear(e, stock_minimo="0")

    r = _ajustar(e, p["id"], "incremento", 100, motivo="Ingreso por conteo inicial")
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert Decimal(cuerpo["existencias"]["stock_actual"]) == 100
    mov = cuerpo["movimiento"]
    assert mov["tipo_movimiento"] == "ajuste" and mov["referencia_tipo"] == "ajuste"
    assert Decimal(mov["cantidad"]) == 100 and Decimal(mov["saldo_resultante"]) == 100
    assert mov["motivo"] == "Ingreso por conteo inicial"
    assert mov["usuario_id"] == str(e.usuario.id)

    r = _ajustar(e, p["id"], "decremento", 30, motivo="Merma por producto dañado")
    assert Decimal(r.json()["movimiento"]["cantidad"]) == -30
    assert Decimal(r.json()["movimiento"]["saldo_resultante"]) == 70

    r = _ajustar(e, p["id"], "fijar", 55, motivo="Inventario físico del cierre")
    assert Decimal(r.json()["movimiento"]["cantidad"]) == -15
    assert Decimal(r.json()["existencias"]["stock_actual"]) == 55

    kardex = e.client.get(
        f"{INVENTARIO}/kardex",
        params={"producto_id": p["id"], "tipo_movimiento": "ajuste"},
        headers=e.h,
    ).json()
    assert kardex["total"] == 3
    assert {k["motivo"] for k in kardex["items"]} == {
        "Ingreso por conteo inicial",
        "Merma por producto dañado",
        "Inventario físico del cierre",
    }
    inv = e.db.scalar(select(Inventario).where(Inventario.producto_id == uuid.UUID(p["id"])))
    assert inv.stock_actual == 55


# TC-AJU-02
def test_ajuste_no_puede_dejar_stock_bajo_lo_reservado_ni_negativo(entorno):
    e = entorno
    p = _crear(e, stock_minimo="0")
    _ajustar(e, p["id"], "incremento", 20)
    inv = e.db.scalar(select(Inventario).where(Inventario.producto_id == uuid.UUID(p["id"])))
    inv.stock_reservado = Decimal("8")
    e.db.commit()

    r = _ajustar(e, p["id"], "decremento", 15)  # 20 - 15 = 5 < 8 reservado
    assert r.status_code == 400 and r.json()["codigo"] == "STOCK_INSUFICIENTE"
    assert Decimal(r.json()["detalle"]["stock_reservado"]) == 8
    r = _ajustar(e, p["id"], "fijar", 7)
    assert r.status_code == 400 and r.json()["codigo"] == "STOCK_INSUFICIENTE"
    r = _ajustar(e, p["id"], "decremento", 500)  # negativo
    assert r.status_code == 400 and r.json()["codigo"] == "STOCK_INSUFICIENTE"
    assert _ajustar(e, p["id"], "decremento", 12).status_code == 201  # 20 - 12 = 8 = reservado

    inv = e.db.scalar(select(Inventario).where(Inventario.producto_id == uuid.UUID(p["id"])))
    assert inv.stock_actual == 8
    # Los rechazos no dejan movimientos: solo el incremento inicial y el decremento válido.
    assert e.db.query(Kardex).filter(Kardex.producto_id == uuid.UUID(p["id"])).count() == 2


# TC-AJU-03
def test_ajuste_validaciones_de_entrada(entorno):
    e = entorno
    p = _crear(e)
    r = _ajustar(e, p["id"], "incremento", 0)
    assert r.status_code == 400 and r.json()["codigo"] == "CANTIDAD_INVALIDA"
    r = _ajustar(e, p["id"], "decremento", 0)
    assert r.status_code == 400 and r.json()["codigo"] == "CANTIDAD_INVALIDA"
    r = _ajustar(e, p["id"], "fijar", 0)  # ya está en 0: sin cambio
    assert r.status_code == 400 and r.json()["codigo"] == "AJUSTE_SIN_CAMBIO"
    assert _ajustar(e, p["id"], "incremento", 5, motivo="abc").status_code == 422  # motivo corto
    assert _ajustar(e, p["id"], "incremento", -3).status_code == 422
    assert _ajustar(e, p["id"], "multiplicar", 3).status_code == 422
    r = _ajustar(e, uuid.uuid4(), "incremento", 3)
    assert r.status_code == 404 and r.json()["codigo"] == "PRODUCTO_NO_ENCONTRADO"


# TC-AJU-03
def test_ajuste_a_producto_inactivo_es_rechazado(entorno):
    e = entorno
    p = _crear(e)
    e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h)
    r = _ajustar(e, p["id"], "incremento", 3)
    assert r.status_code == 409 and r.json()["codigo"] == "PRODUCTO_INACTIVO"
    e.client.post(f"{PRODUCTOS}/{p['id']}/reactivate", headers=e.h)
    assert _ajustar(e, p["id"], "incremento", 3).status_code == 201


# TC-AJU-04
def test_ajuste_bajo_el_minimo_abre_alerta_sin_duplicarla(entorno):
    e = entorno
    p = _crear(e, stock_minimo="50")
    pid = uuid.UUID(p["id"])
    assert _ajustar(e, p["id"], "incremento", 10).status_code == 201
    assert _ajustar(e, p["id"], "incremento", 5).status_code == 201  # sigue bajo el mínimo

    alertas = e.db.scalars(select(Alerta).where(Alerta.producto_id == pid)).all()
    assert len(alertas) == 1
    assert alertas[0].tipo == TipoAlerta.STOCK_BAJO and alertas[0].estado == EstadoAlerta.ABIERTA

    p2 = _crear(e, stock_minimo="5")
    assert _ajustar(e, p2["id"], "incremento", 10).status_code == 201  # sobre el mínimo
    assert not e.db.scalars(select(Alerta).where(Alerta.producto_id == uuid.UUID(p2["id"]))).all()


# ------------------------------------------------------------------ efecto de la baja
# TC-PROD-06
def test_producto_inactivo_queda_fuera_de_existencias_cargas_y_pronosticos(entorno):
    e = entorno
    db = e.db
    p = _crear(e, stock_minimo="100")
    pid = uuid.UUID(p["id"])
    ruta = Ruta(codigo=f"RB-{e.sufijo}", nombre="Ruta baja")
    lote = EtlLote(
        usuario_id=e.usuario.id, archivo_nombre="b.xlsx", checksum_sha256=uuid.uuid4().hex * 2
    )
    db.add_all([ruta, lote])
    db.flush()
    db.add(
        VentaHistorica(
            lote_id=lote.id,
            fecha_venta=date(2025, 3, 1),
            producto_id=pid,
            ruta_id=ruta.id,
            cantidad=Decimal("4"),
            precio_unitario=Decimal("12.50"),
            monto_total=Decimal("50"),
        )
    )
    db.commit()
    assert sales_repo.productos_de_ruta(db, ruta.id) == [pid]
    bajo = e.client.get(INVENTARIO, params={"bajo_minimo": True, "limit": 200}, headers=e.h)
    assert p["id"] in {x["producto_id"] for x in bajo.json()["items"]}

    assert e.client.delete(f"{PRODUCTOS}/{p['id']}", headers=e.h).status_code == 204

    assert sales_repo.productos_de_ruta(db, ruta.id) == []  # no entra en cargas nuevas
    bajo = e.client.get(INVENTARIO, params={"bajo_minimo": True, "limit": 200}, headers=e.h)
    assert p["id"] not in {x["producto_id"] for x in bajo.json()["items"]}  # ni en alertas
    with pytest.raises(AppError) as exc:  # ni en pronósticos nuevos
        prediction_service._validar_catalogo(db, [pid], None)
    assert exc.value.codigo == "PRODUCTO_INACTIVO" and exc.value.status_code == 409

    # El historial de ventas sigue intacto.
    assert db.query(VentaHistorica).filter(VentaHistorica.producto_id == pid).count() == 1


# ------------------------------------------------------------------ concurrencia
# TC-AJU-05
def test_dos_ajustes_simultaneos_no_dejan_stock_negativo():
    """Dos decrementos de 60 sobre un stock de 100: uno debe fallar con `STOCK_INSUFICIENTE`."""
    factory = get_sessionmaker()
    try:
        setup = factory()
        setup.connection()
    except Exception:  # noqa: BLE001 - sin PostgreSQL (psycopg2 en Windows lanza UnicodeDecodeError)
        pytest.skip("PostgreSQL no disponible")

    sufijo = uuid.uuid4().hex[:8]
    categoria = Categoria(nombre=f"cat-conc-{sufijo}")
    usuario = Usuario(
        email=f"conc-{sufijo}@ds.gt", password_hash="x", nombre_completo="Concurrente"
    )
    setup.add_all([categoria, usuario])
    setup.flush()
    producto = Producto(sku=f"CONC-{sufijo}", nombre="Concurrente", categoria_id=categoria.id)
    setup.add(producto)
    setup.flush()
    setup.add(Inventario(producto_id=producto.id, stock_actual=Decimal("100")))
    setup.commit()
    ids = SimpleNamespace(p=producto.id, c=categoria.id, u=usuario.id)
    setup.close()

    resultados: list[str] = []
    barrera = threading.Barrier(2)

    def decrementar() -> None:
        sesion = factory()
        try:
            barrera.wait(timeout=10)
            inventory_service.ajustar_existencias(
                sesion,
                AjusteRequest(
                    producto_id=ids.p,
                    tipo="decremento",
                    cantidad=Decimal("60"),
                    motivo="Salida concurrente",
                ),
                ids.u,
            )
            resultados.append("ok")
        except AppError as exc:
            sesion.rollback()
            resultados.append(exc.codigo)
        finally:
            sesion.close()

    try:
        hilos = [threading.Thread(target=decrementar) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=30)

        assert sorted(resultados) == ["STOCK_INSUFICIENTE", "ok"]
        verif = factory()
        inv = verif.scalar(select(Inventario).where(Inventario.producto_id == ids.p))
        assert inv.stock_actual == 40
        assert verif.query(Kardex).filter(Kardex.producto_id == ids.p).count() == 1
        verif.close()
    finally:
        limpieza = factory()
        limpieza.execute(delete(Alerta).where(Alerta.producto_id == ids.p))
        limpieza.execute(delete(Kardex).where(Kardex.producto_id == ids.p))
        limpieza.execute(delete(Inventario).where(Inventario.producto_id == ids.p))
        limpieza.execute(delete(Producto).where(Producto.id == ids.p))
        limpieza.execute(delete(Categoria).where(Categoria.id == ids.c))
        limpieza.execute(delete(Usuario).where(Usuario.id == ids.u))
        limpieza.commit()
        limpieza.close()
