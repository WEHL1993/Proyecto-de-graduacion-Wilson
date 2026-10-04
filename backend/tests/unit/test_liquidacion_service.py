"""Liquidación diaria (ADR-14) sin base de datos: DTOs, validaciones, cuadres, checksum y
selección de la fuente de entrenamiento. TC-LIQ-01..08 (parte unitaria)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.enums import EstadoLiquidacion, FuenteReentrenamiento, OrigenDatos
from app.domain.models.sales import LiquidacionDetalle, LiquidacionDiaria
from app.schemas.liquidacion import (
    AnulacionRequest,
    LineaLiquidacion,
    LiquidacionRequest,
    PagosLiquidacion,
)
from app.services import liquidacion_service as svc
from app.services import training_service

D = Decimal
P1, P2 = uuid.UUID(int=1), uuid.UUID(int=2)
RUTA, VENDEDOR = uuid.UUID(int=10), uuid.UUID(int=20)


def linea(pid=P1, cargada="20", vendida="15", devuelta="3", merma="2", precio="50", **kw):
    return svc.LineaCalculada(
        producto_id=pid,
        cargada=D(cargada),
        vendida=D(vendida),
        devuelta=D(devuelta),
        merma=D(merma),
        precio=D(precio),
        **kw,
    )


def codigo(excepcion: pytest.ExceptionInfo[AppError]) -> str:
    return excepcion.value.codigo


# ---------------------------------------------------------------- DTO (422)
def _solicitud(**cambios):
    base = {
        "fecha": date(2026, 9, 1),
        "ruta_id": RUTA,
        "lineas": [
            {
                "producto_id": P1,
                "cantidad_cargada": "20",
                "cantidad_vendida": "15",
                "cantidad_devuelta": "3",
                "cantidad_merma": "2",
            }
        ],
    }
    return LiquidacionRequest(**{**base, **cambios})


def test_dto_valido_y_valores_por_defecto():
    s = _solicitud()
    assert s.vendedor_id is None and s.pagos == PagosLiquidacion()
    assert s.lineas[0].precio_unitario is None and s.lineas[0].agotado is False


@pytest.mark.parametrize("campo", ["cantidad_vendida", "cantidad_devuelta", "cantidad_merma"])
def test_dto_rechaza_cantidades_negativas(campo):
    base = {"producto_id": P1, "cantidad_cargada": "5", "cantidad_vendida": "1"}
    with pytest.raises(ValidationError):
        LineaLiquidacion(**{**base, campo: "-1"})


def test_dto_rechaza_montos_negativos_y_mas_de_dos_decimales():
    with pytest.raises(ValidationError):
        PagosLiquidacion(efectivo="-0.01")
    with pytest.raises(ValidationError):
        PagosLiquidacion(gastos="1.234")
    with pytest.raises(ValidationError):
        LineaLiquidacion(producto_id=P1, cantidad_cargada="1.005", cantidad_vendida="1")


def test_dto_rechaza_lista_de_lineas_vacia():
    with pytest.raises(ValidationError):
        _solicitud(lineas=[])


def test_anulacion_exige_motivo_de_al_menos_cinco_caracteres():
    assert AnulacionRequest(motivo="  error de captura ").motivo == "error de captura"
    with pytest.raises(ValidationError):
        AnulacionRequest(motivo="  ab  ")


# ---------------------------------------------------------------- reglas de negocio (400)
def test_fecha_futura_se_rechaza_y_hoy_se_acepta():
    hoy = date(2026, 9, 30)
    svc.validar_fecha(hoy, hoy)
    svc.validar_fecha(date(2026, 9, 1), hoy)
    with pytest.raises(AppError) as exc:
        svc.validar_fecha(date(2026, 10, 1), hoy)
    assert codigo(exc) == "VENTA_FECHA_FUTURA" and exc.value.status_code == 400


def test_producto_duplicado_en_la_liquidacion():
    svc.validar_productos_unicos([P1, P2])
    with pytest.raises(AppError) as exc:
        svc.validar_productos_unicos([P1, P2, P1])
    assert codigo(exc) == "PRODUCTO_DUPLICADO_EN_CIERRE"
    assert exc.value.detalle == {"producto_ids": [str(P1)]}


def test_exige_al_menos_una_linea_con_venta_o_carga():
    svc.validar_hay_movimiento([linea(cargada="0", vendida="0", devuelta="0", merma="0"), linea()])
    with pytest.raises(AppError) as exc:
        svc.validar_hay_movimiento([linea(cargada="0", vendida="0", devuelta="0", merma="0")])
    assert codigo(exc) == "LIQUIDACION_SIN_MOVIMIENTO"


def test_unidades_que_exceden_lo_cargado_no_se_aceptan_ni_como_borrador():
    svc.validar_unidades_no_exceden([linea()])  # 15 + 3 + 2 = 20: cuadra
    svc.validar_unidades_no_exceden([linea(devuelta="1")])  # sobran 4: permitido en borrador
    with pytest.raises(AppError) as exc:
        svc.validar_unidades_no_exceden([linea(vendida="19")], {P1: "3030-PINA"})
    assert codigo(exc) == "UNIDADES_NO_CUADRAN"
    assert exc.value.detalle["productos"]["3030-PINA"]["diferencia"] == "-4"


def test_para_cerrar_cargada_debe_igualar_vendida_devuelta_merma():
    # TC-LIQ-07 (unidades)
    svc.exigir_unidades_cuadran(
        [linea(), linea(pid=P2, cargada="10", vendida="10", devuelta="0", merma="0")]
    )
    with pytest.raises(AppError) as exc:
        svc.exigir_unidades_cuadran([linea(devuelta="1")], {P1: "2250-COLA"})
    assert codigo(exc) == "UNIDADES_NO_CUADRAN"
    assert exc.value.detalle["productos"]["2250-COLA"]["diferencia"] == "2"


def test_monto_es_cantidad_por_precio_con_redondeo_a_centavos():
    assert svc.calcular_monto(D("15"), D("50")) == D("750.00")
    assert svc.calcular_monto(D("2.5"), D("56.35")) == D("140.88")  # 140.875 -> half up
    assert svc.calcular_monto(D("0"), D("56")) == D("0.00")
    assert svc.total_venta([linea(), linea(pid=P2, vendida="10", precio="30")]) == D("1050.00")


def test_efectivo_esperado_y_diferencia_de_caja():
    pagos = PagosLiquidacion(
        efectivo="800", transferencia="150", credito="100", cobro_saldos="50", gastos="20",
        efectivo_entregado="800",
    )  # fmt: skip
    esperado, diferencia = svc.calcular_caja(pagos)
    assert esperado == D("830") and diferencia == D("-30")  # faltante
    assert svc.calcular_caja(PagosLiquidacion(efectivo="100", efectivo_entregado="130")) == (
        D("100"),
        D("30"),
    )  # sobrante


def test_para_cerrar_la_venta_debe_igualar_efectivo_transferencia_credito():
    pagos = PagosLiquidacion(efectivo="800", transferencia="150", credito="100")
    svc.exigir_montos_cuadran(D("1050"), pagos)
    with pytest.raises(AppError) as exc:
        svc.exigir_montos_cuadran(D("1100"), pagos)
    assert codigo(exc) == "MONTOS_NO_CUADRAN"
    assert exc.value.detalle["diferencia"] == "50"


def test_umbral_de_diferencia_usa_valor_absoluto_y_es_estricto():
    umbral = D("10.00")
    assert not svc.supera_umbral(D("10.00"), umbral)
    assert not svc.supera_umbral(D("-9.99"), umbral)
    assert svc.supera_umbral(D("-10.01"), umbral)
    assert svc.supera_umbral(D("10.01"), umbral)


# ---------------------------------------------------------------- checksum del lote
def test_checksum_es_determinista_e_independiente_del_orden_de_las_lineas():
    a, b = linea(P1), linea(P2, vendida="10", devuelta="0", merma="0", cargada="10", precio="30")
    base = svc.calcular_checksum(date(2026, 9, 1), RUTA, VENDEDOR, [a, b])
    assert base == svc.calcular_checksum(date(2026, 9, 1), RUTA, VENDEDOR, [b, a])
    assert len(base) == 64 and int(base, 16) >= 0


@pytest.mark.parametrize(
    "cambio",
    [
        {"fecha": date(2026, 9, 2)},
        {"ruta_id": uuid.UUID(int=11)},
        {"vendedor_id": uuid.UUID(int=21)},
        {"lineas": [linea(vendida="14", devuelta="4")]},
        {"lineas": [linea(precio="51")]},
    ],
)
def test_checksum_cambia_con_cualquier_dato_relevante(cambio):
    parametros = {
        "fecha": date(2026, 9, 1),
        "ruta_id": RUTA,
        "vendedor_id": VENDEDOR,
        "lineas": [linea()],
    }
    original = svc.calcular_checksum(**parametros)
    assert svc.calcular_checksum(**{**parametros, **cambio}) != original


def test_checksum_anulado_libera_el_original_y_depende_de_la_version():
    original = svc.calcular_checksum(date(2026, 9, 1), RUTA, VENDEDOR, [linea()])
    liq = uuid.uuid4()
    sellado = svc.checksum_anulado(original, liq, 1)
    assert sellado != original and len(sellado) == 64
    assert sellado != svc.checksum_anulado(original, liq, 2)


# ---------------------------------------------------------------- respuesta con cuadres
def _liquidacion(estado=EstadoLiquidacion.BORRADOR, **cab) -> LiquidacionDiaria:
    valores = {
        "id": uuid.uuid4(),
        "fecha": date(2026, 9, 1),
        "ruta_id": RUTA,
        "vendedor_id": VENDEDOR,
        "estado": estado,
        "version": 1,
        "venta_total": D("1050"),
        "total_efectivo": D("800"),
        "total_transferencia": D("150"),
        "total_credito": D("100"),
        "cobro_saldos_anteriores": D("50"),
        "gastos_ruta": D("20"),
        "efectivo_esperado": D("830"),
        "efectivo_entregado": D("800"),
        "diferencia_caja": D("-30"),
        "creado_en": datetime.now(UTC),
        **cab,
    }
    liq = LiquidacionDiaria(**valores)
    liq.detalles = [
        LiquidacionDetalle(
            producto_id=P1, cantidad_cargada=D(20), cantidad_vendida=D(15), cantidad_devuelta=D(3),
            cantidad_merma=D(2), precio_unitario=D(50), monto_total=D(750), agotado=True,
        ),
        LiquidacionDetalle(
            producto_id=P2, cantidad_cargada=D(10), cantidad_vendida=D(10), cantidad_devuelta=D(0),
            cantidad_merma=D(0), precio_unitario=D(30), monto_total=D(300), agotado=False,
        ),
    ]  # fmt: skip
    return liq


def test_respuesta_calcula_cuadre_de_unidades_dinero_y_devolucion_esperada():
    r = svc.construir_respuesta(
        _liquidacion(),
        catalogo={P1: ("3030-PINA", "Piña 3L"), P2: ("2250-COLA", "Cola 2.25L")},
        ruta_nombre="Cornelio",
        vendedor_nombre="Cornelio Pérez",
        umbral=D("10.00"),
    )
    assert [ln.sku for ln in r.lineas] == ["2250-COLA", "3030-PINA"]  # ordenadas por SKU
    assert r.cuadre_unidades.cuadra and r.cuadre_unidades.diferencia == 0
    assert r.cuadre_unidades.cargadas == 30 and r.cuadre_unidades.vendidas == 25
    assert r.devolucion_esperada == 3
    assert r.cuadre_dinero.cuadra and r.cuadre_dinero.total_pagos == D("1050")
    assert r.cuadre_dinero.diferencia_caja == D("-30") and r.cuadre_dinero.supera_umbral
    assert r.lineas[1].agotado is True


def test_respuesta_marca_filas_y_dinero_que_no_cuadran():
    liq = _liquidacion(total_credito=D("0"))
    liq.detalles[0].cantidad_devuelta = D(0)
    r = svc.construir_respuesta(
        liq,
        catalogo={P1: ("3030-PINA", "Piña"), P2: ("2250-COLA", "Cola")},
        ruta_nombre="R",
        vendedor_nombre="V",
        umbral=D("100"),
    )
    assert not r.cuadre_unidades.cuadra and r.cuadre_unidades.diferencia == 3
    assert not r.lineas[1].cuadra and r.lineas[0].cuadra
    assert not r.cuadre_dinero.cuadra and r.cuadre_dinero.diferencia_venta_pagos == D("100")
    assert not r.cuadre_dinero.supera_umbral  # |-30| <= 100


# ---------------------------------------------------------------- fuente de entrenamiento
class _Repos:
    """Dobles de los repositorios que lee `training_service._preparar_datos`."""

    def __init__(self, monkeypatch, *, liquidados, base=None, ventas=None):
        self.llamadas: list = []
        ruta = uuid.UUID(int=10)
        base = base or {ruta: (date(2025, 1, 1), date(2025, 3, 31))}
        ventas = ventas or [(date(2025, 1, 1), P1, ruta, D("5"))]
        ventas_liq = [(date(2026, 3, 1), P1, ruta, D("7"))]

        def ventas_diarias(db, **kw):
            self.llamadas.append(kw.get("origenes"))
            origenes = kw.get("origenes")
            if origenes is None:
                return ventas + ventas_liq
            filas = []
            if OrigenDatos.EXCEL_HISTORICO in origenes:
                filas += ventas
            if OrigenDatos.LIQUIDACION in origenes:
                filas += ventas_liq
            return filas

        monkeypatch.setattr(training_service.sales_repo, "ventas_diarias", ventas_diarias)
        monkeypatch.setattr(
            training_service.sales_repo, "rangos_por_ruta_de_origen", lambda db, o: base
        )
        monkeypatch.setattr(
            training_service.sales_repo,
            "resumen_por_origen",
            lambda db: {
                "excel_historico": {
                    "filas": 1,
                    "desde": date(2025, 1, 1),
                    "hasta": date(2025, 3, 31),
                },
                "liquidacion": {"filas": 1, "desde": date(2026, 3, 1), "hasta": date(2026, 3, 1)},
            },
        )  # fmt: skip
        monkeypatch.setattr(
            training_service.liquidacion_repo, "rangos_cerrados_por_ruta", lambda db: liquidados
        )
        monkeypatch.setattr(training_service.liquidacion_repo, "dias_cerrados", lambda db: 60)
        monkeypatch.setattr(
            training_service.liquidacion_repo,
            "censuras",
            lambda db: {(date(2026, 3, 1), P1, ruta)},
        )


RUTA_LIQ = uuid.UUID(int=10)
LIQUIDADOS = {RUTA_LIQ: (date(2026, 3, 1), date(2026, 4, 29))}


def test_entrenamiento_inicial_usa_solo_excel_sin_cobertura(monkeypatch):
    repos = _Repos(monkeypatch, liquidados=LIQUIDADOS)
    ventas, cobertura, fuentes = training_service._preparar_datos(
        None, FuenteReentrenamiento.EXCEL_HISTORICO, None, None
    )
    assert repos.llamadas == [[OrigenDatos.EXCEL_HISTORICO]]
    assert cobertura is None and "censurada" not in ventas.columns and len(ventas) == 1
    assert fuentes["fuente"] == "excel_historico"
    assert set(fuentes["origenes"]) == {"excel_historico"}


def test_mixta_sin_liquidaciones_cerradas_se_comporta_como_el_modo_clasico(monkeypatch):
    repos = _Repos(monkeypatch, liquidados={})
    ventas, cobertura, _ = training_service._preparar_datos(
        None, FuenteReentrenamiento.EXCEL_MAS_LIQUIDACION, None, None
    )
    assert repos.llamadas == [None] and cobertura is None and "censurada" not in ventas.columns


def test_mixta_con_liquidaciones_usa_ambos_origenes_cobertura_y_censura(monkeypatch):
    repos = _Repos(monkeypatch, liquidados=LIQUIDADOS)
    ventas, cobertura, fuentes = training_service._preparar_datos(
        None, FuenteReentrenamiento.EXCEL_MAS_LIQUIDACION, None, None
    )
    assert repos.llamadas == [[OrigenDatos.EXCEL_HISTORICO, OrigenDatos.LIQUIDACION]]
    assert cobertura == {
        str(RUTA_LIQ): [
            (date(2025, 1, 1), date(2025, 3, 31)),
            (date(2026, 3, 1), date(2026, 4, 29)),
        ]
    }
    assert list(ventas["censurada"]) == [0.0, 1.0]  # solo el día liquidado como agotado
    assert set(fuentes["origenes"]) == {"excel_historico", "liquidacion"}
    assert fuentes["dias_liquidados"] == 60


def test_solo_liquidacion_excluye_el_excel(monkeypatch):
    repos = _Repos(monkeypatch, liquidados=LIQUIDADOS)
    ventas, cobertura, _ = training_service._preparar_datos(
        None, FuenteReentrenamiento.LIQUIDACION, None, None
    )
    assert repos.llamadas == [[OrigenDatos.LIQUIDACION]]
    assert cobertura == {str(RUTA_LIQ): [(date(2026, 3, 1), date(2026, 4, 29))]}
    assert len(ventas) == 1


def test_solo_liquidacion_con_menos_de_28_dias_es_historial_insuficiente(monkeypatch):
    _Repos(monkeypatch, liquidados={RUTA_LIQ: (date(2026, 3, 1), date(2026, 3, 20))})
    with pytest.raises(AppError) as exc:
        training_service._preparar_datos(None, FuenteReentrenamiento.LIQUIDACION, None, None)
    assert exc.value.codigo == "HISTORIAL_INSUFICIENTE"
    assert exc.value.detalle["rutas_con_menos_dias"] == {str(RUTA_LIQ): 20}


def test_solo_liquidacion_sin_ninguna_liquidacion_es_historial_insuficiente(monkeypatch):
    _Repos(monkeypatch, liquidados={})
    with pytest.raises(AppError) as exc:
        training_service._preparar_datos(None, FuenteReentrenamiento.LIQUIDACION, None, None)
    assert exc.value.codigo == "HISTORIAL_INSUFICIENTE"
