"""Pruebas sin BD del ETL: lectura/normalización de Excel y validación contra catálogo (fake).

Cubre la parte pura de TC-ETL-01 (errores por fila/columna) y el formato ancho real.
"""

import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.repositories import catalog_repo, user_repo
from app.repositories.catalog_repo import RutaResuelta
from app.schemas.etl import CodigoErrorEtl
from app.services import etl_lectura, etl_service
from app.services.etl_lectura import ArchivoInvalido, leer_excel, sku_desde_medida_sabor

RAIZ = Path(__file__).resolve().parents[3]
EXCEL_REAL = RAIZ / "data" / "raw" / "VENTAS DIARIAS MARZO 2025.xlsx"


def _xlsx(hojas: dict[str, list[list]]) -> bytes:
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, filas in hojas.items():
        hoja = libro.create_sheet(nombre)
        for fila in filas:
            hoja.append(fila)
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


CABECERA = ["fecha", "ruta", "sku", "cantidad", "precio_unitario"]


def test_tabular_valido_normaliza_filas_y_monto():
    contenido = _xlsx({"Ventas": [CABECERA, [date(2026, 1, 5), "R01", "P-1", 3, 10.5]]})
    lectura = leer_excel(contenido, nombre_archivo="v.xlsx")

    assert lectura.formato == etl_lectura.FORMATO_TABULAR
    assert lectura.errores == []
    (fila,) = lectura.filas
    assert (fila.fecha, fila.ruta, fila.sku) == (date(2026, 1, 5), "R01", "P-1")
    assert fila.monto_total == Decimal("31.50")


def test_tabular_acepta_alias_y_cabeceras_con_acentos():
    cabecera = ["Fecha Venta", "Código Ruta", "SKU", "Unidades", "Precio"]
    contenido = _xlsx({"H": [cabecera, ["05/01/2026", "R01", "P-1", 2, 5]]})
    lectura = leer_excel(contenido, nombre_archivo="v.xlsx")
    assert lectura.errores == []
    assert lectura.filas[0].fecha == date(2026, 1, 5)


def test_tabular_columna_faltante_reporta_por_columna_y_sigue_validando_filas():
    """TC-ETL-01: sin `cantidad`, fila 15 con fecha 31/02/2026."""
    cabecera = ["fecha", "ruta", "sku", "precio_unitario"]
    filas = [cabecera] + [[date(2026, 1, 1), "R01", "P-1", 5] for _ in range(13)]
    filas.append(["31/02/2026", "R01", "P-1", 5])  # fila 15 de Excel
    lectura = leer_excel(_xlsx({"H": filas}), nombre_archivo="v.xlsx")

    assert lectura.columnas_faltantes == ["cantidad"]
    faltante = next(e for e in lectura.errores if e.categoria == CodigoErrorEtl.COLUMNAS_FALTANTES)
    assert (faltante.fila, faltante.columna) == (1, "cantidad")
    fecha = next(e for e in lectura.errores if e.columna == "fecha")
    assert (fecha.fila, fecha.valor) == (15, "31/02/2026")
    assert lectura.filas == []


def test_tabular_valores_invalidos_indican_fila_y_columna_de_excel():
    """TC-ETL-01: fila 15 fecha imposible y fila 22 cantidad -5."""
    filas = [CABECERA] + [[date(2026, 1, 1), "R01", "P-1", 1, 5] for _ in range(21)]
    filas[14] = ["31/02/2026", "R01", "P-1", 1, 5]
    filas[21] = [date(2026, 1, 1), "R01", "P-1", -5, 5]
    lectura = leer_excel(_xlsx({"H": filas}), nombre_archivo="v.xlsx")

    por_fila = {(e.fila, e.columna): e for e in lectura.errores}
    assert por_fila[(15, "fecha")].categoria == CodigoErrorEtl.TIPOS_INVALIDOS
    assert por_fila[(22, "cantidad")].categoria == CodigoErrorEtl.DATOS_INVALIDOS
    assert por_fila[(22, "cantidad")].valor == "-5"
    assert len(lectura.errores) == 2
    assert lectura.filas_totales == 21
    assert len(lectura.filas) == 19


def test_tabular_ignora_filas_vacias_sin_alterar_la_numeracion():
    filas = [CABECERA, [None] * 5, [date(2026, 1, 1), "R01", "P-1", "abc", 5]]
    lectura = leer_excel(_xlsx({"H": filas}), nombre_archivo="v.xlsx")
    assert lectura.filas_totales == 1
    assert (lectura.errores[0].fila, lectura.errores[0].columna) == (3, "cantidad")


def test_archivo_que_no_es_xlsx_lanza_archivo_invalido():
    with pytest.raises(ArchivoInvalido) as exc:
        leer_excel(b"esto no es un excel", nombre_archivo="v.xlsx")
    assert exc.value.codigo == "ARCHIVO_INVALIDO"


def test_hoja_inexistente_lanza_error():
    contenido = _xlsx({"H": [CABECERA]})
    with pytest.raises(ArchivoInvalido) as exc:
        leer_excel(contenido, nombre_archivo="v.xlsx", hoja="Otra")
    assert exc.value.codigo == "HOJA_NO_ENCONTRADA"


# ------------------------------------------------------------------ formato ancho
def _hoja_ancha() -> list[list]:
    cabecera = ["Articulo", "Descripcion", "Precio", None, "Carga 01", "ventas 01", "ventas 31"]
    return [
        cabecera,
        [3030, "Piña", 56, None, None, 2, 1],
        [3030, "Cola", 61, None, None, 0, None],  # sin ventas: no genera registro
        [None, "PULPIN PERA", 15, None, None, 4, None],
        [None, None, None, 4695.95, None, None, None],  # fila de totales
        ["Nit", 110203550, None, None, None, None, None],  # metadatos
    ]


def test_ancho_genera_un_registro_por_dia_con_venta_y_omite_metadatos():
    contenido = _xlsx({"Cornelio": _hoja_ancha(), "clientes": [["PRODUCTO", "X"]]})
    lectura = leer_excel(contenido, nombre_archivo="VENTAS DIARIAS MARZO 2025.xlsx")

    assert lectura.formato == etl_lectura.FORMATO_ANCHO
    assert lectura.errores == []
    assert {(f.fecha, f.sku, f.cantidad) for f in lectura.filas} == {
        (date(2025, 3, 1), "3030-PINA", Decimal("2.00")),
        (date(2025, 3, 31), "3030-PINA", Decimal("1.00")),
        (date(2025, 3, 1), "SM-PULPIN_PERA", Decimal("4.00")),
    }
    assert all(f.ruta == "Cornelio" for f in lectura.filas)
    assert any("clientes" in a for a in lectura.advertencias)


def test_ancho_dia_inexistente_en_el_mes_es_error():
    contenido = _xlsx({"Cornelio": _hoja_ancha()})
    lectura = leer_excel(contenido, nombre_archivo="ventas.xlsx", periodo="2025-04")
    (error,) = lectura.errores
    assert (error.hoja, error.fila, error.columna) == ("Cornelio", 2, "ventas 31")
    assert len(lectura.filas) == 2


def test_ancho_sin_periodo_deducible_pide_el_campo():
    with pytest.raises(ArchivoInvalido) as exc:
        leer_excel(_xlsx({"Cornelio": _hoja_ancha()}), nombre_archivo="ventas.xlsx")
    assert exc.value.codigo == "PERIODO_NO_DETECTADO"


def test_periodo_desde_nombre():
    assert etl_lectura.periodo_desde_nombre("VENTAS DIARIAS MARZO 2025.xlsx") == "2025-03"
    assert etl_lectura.periodo_desde_nombre("ventas.xlsx") is None


def test_sku_desde_medida_sabor():
    assert sku_desde_medida_sabor(3030, "Piña") == "3030-PINA"
    assert sku_desde_medida_sabor(1.3, "Cola  8 un") == "1.3-COLA_8_UN"
    assert sku_desde_medida_sabor(None, "PULPIN PERA") == "SM-PULPIN_PERA"


@pytest.mark.skipif(not EXCEL_REAL.exists(), reason="data/raw no disponible")
def test_excel_real_de_ventas_diarias_se_lee_sin_errores():
    lectura = leer_excel(EXCEL_REAL.read_bytes(), nombre_archivo=EXCEL_REAL.name)

    assert lectura.formato == etl_lectura.FORMATO_ANCHO
    assert lectura.errores == []
    assert {f.hoja for f in lectura.filas} == {"Cornelio", "Antonio", "Cesar"}
    assert len(lectura.filas) == lectura.filas_totales > 1000
    assert min(f.fecha for f in lectura.filas) >= date(2025, 3, 1)
    assert max(f.fecha for f in lectura.filas) <= date(2025, 3, 31)


# ------------------------------------------------------------------ validación (catálogo simulado)
def test_validar_resuelve_ids_agrega_duplicados_y_reporta_desconocidos(monkeypatch):
    producto, ruta, vendedor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(catalog_repo, "mapear_skus", lambda db, skus: {"P-1": producto})
    monkeypatch.setattr(
        catalog_repo, "mapear_rutas", lambda db, c: {"r01": RutaResuelta(ruta, vendedor)}
    )
    monkeypatch.setattr(user_repo, "mapear_por_identificador", lambda db, i: {})

    filas = [
        [date(2026, 1, 1), "R01", "p-1", 2, 10],
        [date(2026, 1, 1), "R01", "P-1", 3, 20],  # misma clave: se suma
        [date(2026, 1, 1), "R99", "P-1", 1, 10],  # ruta desconocida
        [date(2026, 1, 1), "R01", "P-X", 1, 10],  # SKU desconocido
    ]
    lectura = leer_excel(_xlsx({"H": [CABECERA, *filas]}), nombre_archivo="v.xlsx")
    errores, ventas, rechazadas, advertencias = etl_service._validar(None, lectura)

    assert {(e.fila, e.columna) for e in errores} == {(4, "ruta"), (5, "sku")}
    assert rechazadas == 2
    (venta,) = ventas.values()
    assert venta["cantidad"] == Decimal("5.00")
    assert venta["monto"] == Decimal("80.00")
    assert any("sumaron" in a for a in advertencias)
    assert list(ventas)[0][3] == vendedor  # sin columna vendedor: hereda el de la ruta


def test_checksum_sha256_es_determinista():
    assert etl_service.calcular_checksum(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
