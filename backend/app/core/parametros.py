"""Claves y valores por defecto de `parametros_sistema` ligados a la política de datos (ADR-14).

Los demás umbrales (`ml.mape_umbral`, `ml.periodos_consecutivos`, `comisiones.porcentaje`)
viven junto al servicio que los usa.
"""

from decimal import Decimal

# ETL: false una vez cerrado el arranque; las ventas nuevas entran solo por la liquidación diaria.
CARGA_EXCEL_HABILITADA = "etl.carga_excel_habilitada"
# Qué ventas alimentan el reentrenamiento: ver `domain.enums.FuenteReentrenamiento`.
FUENTE_REENTRENAMIENTO = "ml.fuente_reentrenamiento"
# Diferencia de caja (en valor absoluto) a partir de la cual se genera la alerta.
UMBRAL_DIFERENCIA_CAJA = "liquidacion.umbral_diferencia_caja"

CARGA_EXCEL_HABILITADA_POR_DEFECTO = True
FUENTE_REENTRENAMIENTO_POR_DEFECTO = "excel_mas_liquidacion"
UMBRAL_DIFERENCIA_CAJA_POR_DEFECTO = Decimal("10.00")
