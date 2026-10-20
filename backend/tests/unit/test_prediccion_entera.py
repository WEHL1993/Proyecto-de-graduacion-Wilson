"""La demanda agregada se entrega en paquetes enteros y el intervalo contiene al punto."""

from datetime import date

from app.ml.contracts import PuntoPronostico
from app.services.prediction_service import _agregar_por_producto


def _punto(ruta: str, demanda: float, inferior: float, superior: float) -> PuntoPronostico:
    return PuntoPronostico("p", ruta, date(2026, 10, 21), 1, demanda, inferior, superior)


def test_suma_de_rutas_se_redondea_a_entero_con_intervalo_que_lo_contiene():
    (punto,) = _agregar_por_producto(
        [_punto("a", 2.3, 0.4, 4.1), _punto("b", 2.2, 0.9, 3.6)]
    )["p"]
    assert punto.demanda == 5.0  # 4.5 → mitad hacia arriba
    assert punto.inferior == int(punto.inferior) <= punto.demanda
    assert punto.superior == int(punto.superior) >= punto.demanda
