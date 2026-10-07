"""Interpretación de descripciones de `CODIGOS Y PRECIOS` (M02): casos reales y bordes."""

import pytest

from app.db.seeds.catalogo_parser import interpretar_descripcion

# (descripción, medida_ml, unidades, sabor)
CASOS_REALES = [
    ("BIG COLA PET NO RETORNABLE 3030 ML 6", 3030, 6, "COLA"),
    ("BIG COLA PET NO RETORNABLE 3300 ml 6 pack", 3300, 6, "COLA"),
    ("VOLT GO PET NO RETORNABLE 625 ml 12 pack", 625, 12, "GO"),
    ("BIO ALOE VERA NATURAL 500 ML  6 PACK", 500, 6, "ALOE VERA NATURAL"),
    ("PULP ARANDANO TETRA PACK 1000 ML 6", 1000, 6, "ARANDANO"),
    ("BIO AMAYU ARANDANO VIDRIO NO RETORNABLE 300 ML 6 MC", 300, 6, "AMAYU ARANDANO"),
    ("BIG LIMA LIMON REGULAR PET NO RETORNABLE 1300 ML 8", 1300, 8, "LIMA LIMON"),
    (
        "CIFRUT NARANJA, MANDARINA Y LIMON PET NO RETORNABLE 3500 ML 6",
        3500,
        6,
        "NARANJA, MANDARINA Y LIMON",
    ),
]


@pytest.mark.parametrize(("texto", "medida", "unidades", "sabor"), CASOS_REALES)
def test_descripciones_reales(texto, medida, unidades, sabor):
    d = interpretar_descripcion(texto)
    assert (d.medida_ml, d.unidades_por_paquete, d.sabor) == (medida, unidades, sabor)
    assert d.avisos == []


def test_sin_medida_en_ml_deja_null_y_avisa():
    d = interpretar_descripcion("CIFRUT FRESA DISPLAY 70 GRS 12 MC")
    assert d.medida_ml is None
    assert d.unidades_por_paquete == 12
    assert d.sabor == "FRESA"
    assert any(a.startswith("sin_medida_ml") for a in d.avisos)


def test_1_5_ml_se_interpreta_como_litros_y_avisa():
    d = interpretar_descripcion("DEPORADE UVA PET NO RETORNABLE 1.5ML 6")
    assert d.medida_ml == 1500 and d.unidades_por_paquete == 6
    assert any(a.startswith("medida_en_litros") for a in d.avisos)


def test_litros_explicitos_se_convierten_a_ml():
    d = interpretar_descripcion("BIG COLA PET 2 L 6")
    assert d.medida_ml == 2000 and d.unidades_por_paquete == 6
    assert any(a.startswith("medida_en_litros") for a in d.avisos)


def test_mojibake_de_pina_se_corrige_y_se_avisa():
    d = interpretar_descripcion("BIG PI�A PET NO RETORNABLE 3030 ML 6")
    assert d.sabor == "PIÑA" and "PIÑA" in d.nombre and "�" not in d.nombre
    assert any(a.startswith("caracter_corregido") for a in d.avisos)


def test_otro_caracter_ilegible_se_conserva_y_se_avisa():
    d = interpretar_descripcion("BIG NARANJ� PET 3030 ML 6")
    assert "�" in d.nombre
    assert any(a.startswith("caracter_ilegible") for a in d.avisos)


def test_sin_unidades_asume_uno_y_avisa():
    d = interpretar_descripcion("BIG COLA PET NO RETORNABLE 3030 ML")
    assert d.unidades_por_paquete == 1
    assert any(a.startswith("sin_unidades_por_paquete") for a in d.avisos)


def test_sin_medida_alguna_avisa_y_conserva_unidades_finales():
    d = interpretar_descripcion("CIELO AGUA 12 PACK")
    assert d.medida_ml is None and d.unidades_por_paquete == 12
    assert any(a.startswith("sin_medida:") for a in d.avisos)


def test_el_sabor_largo_se_trunca_con_aviso():
    d = interpretar_descripcion("MARCA " + "SABOR " * 20 + "PET 500 ML 6")
    assert len(d.sabor) <= 60
    assert any(a.startswith("sabor_truncado") for a in d.avisos)
