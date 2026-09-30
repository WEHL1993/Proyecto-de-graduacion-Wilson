"""Pruebas de integración de `POST /etl/upload-excel` contra PostgreSQL real.

Cubre TC-ETL-01 (rechazo con errores por fila/columna), TC-ETL-02 (lote duplicado),
TC-ETL-03 (10 000 filas e idempotencia) y TC-ETL-04 (RBAC), más carga parcial, comisiones,
reproceso de un lote rechazado y el formato ancho. Requiere la BD migrada; se omiten si no
hay conexión. Cada prueba corre en una transacción que se revierte al final.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import get_db, get_engine
from app.core.security import create_access_token, hash_password
from app.domain.models.auth import Permiso, Rol, Usuario
from app.domain.models.catalog import Categoria, Producto, Ruta
from app.domain.models.ml import Alerta, ParametroSistema
from app.domain.models.sales import Comision, EtlLote, VentaHistorica
from app.main import app

URL = "/api/v1/etl/upload-excel"
CABECERA = ["fecha", "ruta", "sku", "cantidad", "precio_unitario"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ------------------------------------------------------------------ fixtures
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
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _crear_usuario(db: Session, email: str, permisos: list[str]) -> Usuario:
    permisos_orm = []
    for codigo in permisos:
        permiso = db.scalar(select(Permiso).where(Permiso.codigo == codigo))
        permisos_orm.append(permiso or Permiso(codigo=codigo, descripcion=codigo))
    rol = Rol(
        nombre=f"rol-{uuid.uuid4().hex[:8]}", descripcion="rol de prueba", permisos=permisos_orm
    )
    usuario = Usuario(
        email=email,
        password_hash=hash_password("ClaveSegura123"),
        nombre_completo=f"Usuario {email}",
        roles=[rol],
    )
    db.add(usuario)
    db.flush()
    return usuario


def _auth(usuario: Usuario) -> dict[str, str]:
    perms = sorted({p.codigo for r in usuario.roles for p in r.permisos})
    token, _ = create_access_token(sub=str(usuario.id), roles=[], perms=perms)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cargador(db_session):
    return _crear_usuario(db_session, "etl@ds.gt", ["etl:cargar"])


@pytest.fixture
def catalogo(db_session):
    """Un vendedor, la ruta R01 asignada a él y los productos P-1 y P-2."""
    vendedor = _crear_usuario(db_session, "vendedor-etl@ds.gt", [])
    categoria = Categoria(nombre=f"cat-{uuid.uuid4().hex[:8]}")
    db_session.add(categoria)
    db_session.flush()
    ruta = Ruta(codigo="R01", nombre="Cornelio", vendedor_id=vendedor.id)
    productos = [
        Producto(sku=f"P-{i}", nombre=f"Producto {i}", categoria_id=categoria.id) for i in (1, 2)
    ]
    db_session.add_all([ruta, *productos])
    db_session.flush()
    return {"vendedor": vendedor, "ruta": ruta, "productos": productos, "categoria": categoria}


def _xlsx(filas: list[list], nombre_hoja: str = "Ventas") -> bytes:
    libro = Workbook()
    libro.active.title = nombre_hoja
    for fila in filas:
        libro.active.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _subir(client, usuario, contenido, *, nombre="ventas.xlsx", **campos):
    return client.post(
        URL, headers=_auth(usuario), files={"file": (nombre, contenido, XLSX)}, data=campos
    )


def _ventas(db: Session, ruta: Ruta) -> list[VentaHistorica]:
    return list(db.scalars(select(VentaHistorica).where(VentaHistorica.ruta_id == ruta.id)))


def _valido(dia: int = 1, sku: str = "P-1", cantidad=4, precio=10.5) -> list:
    return [date(2026, 1, dia), "R01", sku, cantidad, precio]


# ------------------------------------------------------------------ TC-ETL-01
def test_tc_etl_01_columna_faltante_y_datos_invalidos_rechazan_el_lote(
    client, db_session, cargador, catalogo
):
    filas = [["fecha", "ruta", "sku", "precio_unitario"]]  # sin `cantidad`
    filas += [[date(2026, 1, 1), "R01", "P-1", 10] for _ in range(13)]
    filas.append(["31/02/2026", "R01", "P-1", 10])  # fila 15
    respuesta = _subir(client, cargador, _xlsx(filas), modo="estricto")

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "COLUMNAS_FALTANTES"
    errores = {(e["fila"], e["columna"]) for e in cuerpo["errores"]}
    assert (1, "cantidad") in errores
    assert (15, "fecha") in errores

    lote = db_session.get(EtlLote, uuid.UUID(cuerpo["lote_id"]))
    assert lote.estado == "rechazado"
    assert lote.errores  # poblado
    assert _ventas(db_session, catalogo["ruta"]) == []
    assert db_session.scalar(select(func.count()).where(Alerta.tipo == "etl_error")) >= 1


def test_tc_etl_01_fila_15_fecha_imposible_y_fila_22_cantidad_negativa(
    client, db_session, cargador, catalogo
):
    filas = [CABECERA] + [_valido() for _ in range(21)]
    filas[14] = ["31/02/2026", "R01", "P-1", 1, 10]
    filas[21] = _valido(cantidad=-5)
    respuesta = _subir(client, cargador, _xlsx(filas))

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "DATOS_INVALIDOS"
    por_celda = {(e["fila"], e["columna"]): e for e in cuerpo["errores"]}
    assert por_celda[(15, "fecha")]["valor"] == "31/02/2026"
    assert por_celda[(22, "cantidad")]["valor"] == "-5"
    assert cuerpo["total_errores"] == 2
    assert _ventas(db_session, catalogo["ruta"]) == []


def test_sku_y_ruta_desconocidos_rechazan_en_modo_estricto(client, db_session, cargador, catalogo):
    filas = [CABECERA, _valido(sku="NO-EXISTE"), [date(2026, 1, 1), "R99", "P-1", 1, 5]]
    respuesta = _subir(client, cargador, _xlsx(filas))

    assert respuesta.status_code == 422
    columnas = {(e["fila"], e["columna"]) for e in respuesta.json()["errores"]}
    assert columnas == {(2, "sku"), (3, "ruta")}


# ------------------------------------------------------------------ TC-ETL-02
def test_tc_etl_02_mismo_archivo_devuelve_400_lote_duplicado(
    client, db_session, cargador, catalogo
):
    contenido = _xlsx([CABECERA, _valido()])
    primera = _subir(client, cargador, contenido)
    assert primera.status_code == 200

    segunda = _subir(client, cargador, contenido)

    assert segunda.status_code == 400
    assert segunda.json()["codigo"] == "LOTE_DUPLICADO"
    assert len(_ventas(db_session, catalogo["ruta"])) == 1


# ------------------------------------------------------------------ TC-ETL-03
def test_tc_etl_03_diez_mil_filas_se_cargan_y_la_recarga_no_duplica(
    client, db_session, cargador, catalogo
):
    db_session.add_all(
        Producto(sku=f"M-{i:03d}", nombre=f"Masivo {i}", categoria_id=catalogo["categoria"].id)
        for i in range(100)
    )
    db_session.flush()
    inicio = date(2026, 1, 1)
    filas = [
        [inicio + timedelta(days=d), "R01", f"M-{p:03d}", d + p + 1, 5]
        for d in range(100)
        for p in range(100)
    ]
    respuesta = _subir(client, cargador, _xlsx([CABECERA, *filas]))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert (cuerpo["estado"], cuerpo["filas_validas"], cuerpo["filas_rechazadas"]) == (
        "cargado",
        10000,
        0,
    )
    assert cuerpo["rango_fechas"] == {"desde": "2026-01-01", "hasta": "2026-04-10"}
    assert len(_ventas(db_session, catalogo["ruta"])) == 10000

    # Archivo distinto (otro checksum) con las mismas claves: ON CONFLICT actualiza.
    filas[0][3] = 999
    recarga = _subir(client, cargador, _xlsx([CABECERA, *filas]), nombre="ventas-v2.xlsx")
    assert recarga.status_code == 200
    ventas = _ventas(db_session, catalogo["ruta"])
    assert len(ventas) == 10000
    assert {v.lote_id for v in ventas} == {uuid.UUID(recarga.json()["lote_id"])}
    assert max(v.cantidad for v in ventas) == Decimal("999.00")


# ------------------------------------------------------------------ TC-ETL-04
def test_tc_etl_04_usuario_sin_permiso_recibe_403_y_no_se_crea_lote(client, db_session, catalogo):
    bodega = _crear_usuario(db_session, "bodega-etl@ds.gt", ["inventario:leer"])
    lotes_antes = db_session.scalar(select(func.count()).select_from(EtlLote))

    respuesta = _subir(client, bodega, _xlsx([CABECERA, _valido()]))

    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "PERMISO_DENEGADO"
    assert db_session.scalar(select(func.count()).select_from(EtlLote)) == lotes_antes


def test_sin_token_devuelve_401(client):
    respuesta = client.post(URL, files={"file": ("v.xlsx", b"x", XLSX)})
    assert respuesta.status_code == 401


# ------------------------------------------------------------------ otros comportamientos
def test_modo_parcial_carga_las_filas_validas_y_registra_las_rechazadas(
    client, db_session, cargador, catalogo
):
    filas = [CABECERA, _valido(1), _valido(2, cantidad=-1), _valido(3)]
    respuesta = _subir(client, cargador, _xlsx(filas), modo="parcial")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["filas_totales"], cuerpo["filas_validas"], cuerpo["filas_rechazadas"]) == (
        3,
        2,
        1,
    )
    assert len(_ventas(db_session, catalogo["ruta"])) == 2
    lote = db_session.get(EtlLote, uuid.UUID(cuerpo["lote_id"]))
    assert lote.estado == "cargado"
    assert lote.errores[0]["fila"] == 3


def test_filas_repetidas_en_el_archivo_se_suman(client, db_session, cargador, catalogo):
    filas = [CABECERA, _valido(cantidad=2, precio=10), _valido(cantidad=3, precio=20)]
    respuesta = _subir(client, cargador, _xlsx(filas))

    assert respuesta.status_code == 200
    (venta,) = _ventas(db_session, catalogo["ruta"])
    assert (venta.cantidad, venta.monto_total, venta.precio_unitario) == (
        Decimal("5.00"),
        Decimal("80.00"),
        Decimal("16.00"),
    )
    assert any("sumaron" in a for a in respuesta.json()["advertencias"])


def test_comisiones_se_calculan_con_el_porcentaje_configurado_y_no_se_duplican(
    client, db_session, cargador, catalogo
):
    db_session.add(ParametroSistema(clave="comisiones.porcentaje", valor=2.5))
    db_session.flush()
    _subir(client, cargador, _xlsx([CABECERA, _valido(cantidad=10, precio=10)]))
    # Recarga con otra cantidad: la comisión se recalcula sobre la misma venta.
    _subir(client, cargador, _xlsx([CABECERA, _valido(cantidad=20, precio=10)]), nombre="v2.xlsx")

    (venta,) = _ventas(db_session, catalogo["ruta"])
    (comision,) = db_session.scalars(select(Comision).where(Comision.venta_id == venta.id))
    assert comision.vendedor_id == catalogo["vendedor"].id
    assert comision.periodo == "2026-01"
    assert comision.porcentaje == Decimal("2.500")
    assert comision.monto == Decimal("5.00")  # 200.00 × 2.5 %


def test_sin_parametro_de_comision_carga_y_advierte(client, db_session, cargador, catalogo):
    db_session.query(ParametroSistema).filter_by(clave="comisiones.porcentaje").delete()
    respuesta = _subir(client, cargador, _xlsx([CABECERA, _valido()]))

    assert respuesta.status_code == 200
    assert any("comisiones.porcentaje" in a for a in respuesta.json()["advertencias"])
    assert db_session.scalar(select(func.count()).select_from(Comision)) == 0


def test_un_lote_rechazado_permite_reprocesar_el_mismo_archivo(
    client, db_session, cargador, catalogo
):
    contenido = _xlsx([CABECERA, _valido(sku="P-9")])
    rechazado = _subir(client, cargador, contenido)
    assert rechazado.status_code == 422

    db_session.add(Producto(sku="P-9", nombre="Nuevo", categoria_id=catalogo["categoria"].id))
    db_session.flush()
    reproceso = _subir(client, cargador, contenido)

    assert reproceso.status_code == 200
    assert reproceso.json()["lote_id"] == rechazado.json()["lote_id"]
    assert len(_ventas(db_session, catalogo["ruta"])) == 1


def test_archivo_que_no_es_xlsx_devuelve_400(client, cargador):
    respuesta = _subir(client, cargador, b"no soy un excel")
    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "ARCHIVO_INVALIDO"


def test_extension_distinta_de_xlsx_devuelve_400(client, cargador):
    respuesta = _subir(client, cargador, b"a,b,c", nombre="ventas.csv")
    assert respuesta.status_code == 400


def test_formato_ancho_mapea_hoja_a_ruta_y_producto_por_medida_y_sabor(
    client, db_session, cargador, catalogo
):
    db_session.add(
        Producto(sku="3030-PINA", nombre="Piña 3030", categoria_id=catalogo["categoria"].id)
    )
    db_session.flush()
    cabecera = ["Articulo", "Descripcion", "Precio", None, "Carga 01", "ventas 01", "ventas 02"]
    hoja = [cabecera, [3030, "Piña", 56, None, None, 2, 3]]
    respuesta = _subir(
        client, cargador, _xlsx(hoja, nombre_hoja="Cornelio"), nombre="VENTAS MARZO 2025.xlsx"
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["filas_validas"] == 2
    assert cuerpo["rango_fechas"] == {"desde": "2025-03-01", "hasta": "2025-03-02"}
    ventas = sorted(_ventas(db_session, catalogo["ruta"]), key=lambda v: v.fecha_venta)
    assert [v.cantidad for v in ventas] == [Decimal("2.00"), Decimal("3.00")]
    assert ventas[0].vendedor_id == catalogo["vendedor"].id
