"""Propuesta de alias Excel -> SKU (M02): empate por medida y palabras del sabor."""

from app.db.seeds.empate_alias import Candidato, medida_y_palabras, proponer
from app.db.seeds.importar_catalogos import HOJAS_RUTA

CATALOGO = [
    Candidato("500179", "BIG COLA PET NO RETORNABLE 3030 ML 6", 3030, 6),
    Candidato("501540", "BIG UVA PET NO RETORNABLE 3030 ML 6", 3030, 6),
    Candidato("500390", "BIG COLA REGULAR PET NO RETORNABLE 1300 ML 8", 1300, 8),
    Candidato("500391", "BIG COLA REGULAR PET NO RETORNABLE 1300 ML 12", 1300, 12),
    Candidato("509919", "CIFRUT SANDIA - PIÑA - FRESA REGULAR PET 1300 ML 8", 1300, 8),
]


def test_medida_en_litros_se_convierte_a_ml():
    assert medida_y_palabras("1.3-COLA_8_UN") == (1300, ["cola"], [8])
    assert medida_y_palabras("3030-PINA") == (3030, ["pina"], [])


def test_sin_medida_no_filtra_por_ml():
    assert medida_y_palabras("SM-PULPIN_PERA")[0] is None


def test_empate_unico_por_medida_y_sabor():
    p = proponer("3030-COLA", CATALOGO)
    assert p.estado == "unico"
    assert p.candidatos[0].sku == "500179"


def test_numero_desempata_por_unidades_por_paquete():
    p = proponer("1.3-COLA_8_UN", CATALOGO)
    assert p.estado == "unico"
    assert p.candidatos[0].sku == "500390"


def test_sin_candidato_cuando_el_sabor_no_esta_en_el_catalogo():
    assert proponer("3030-MANGO", CATALOGO).estado == "sin_candidato"


def test_ambiguo_cuando_varios_productos_cumplen():
    assert proponer("1.3-COLA", CATALOGO).estado == "ambiguo"


def test_importador_reconoce_las_rutas_de_2026():
    assert {"Trakas", "MESSI"} <= set(HOJAS_RUTA)


def test_sinonimos_corrigen_errores_de_escritura_del_excel():
    catalogo = [
        Candidato("599033", "DEPORADE FRUIT PUNCH PET NO RETORNABLE 625 ML 8", 625, 8),
        Candidato("599032", "DEPORADE BLUEBERRY PET NO RETORNABLE 625 ML 8", 625, 8),
    ]
    assert proponer("625-DEPORADE_FRUTY", catalogo).candidatos[0].sku == "599033"
    assert proponer("625-SPORADE_FRUTY", catalogo).estado == "unico"
    assert proponer("625-DEPORADE_BLUE_BERRY", catalogo).candidatos[0].sku == "599032"
