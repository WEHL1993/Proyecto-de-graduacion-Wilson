"""Enumeraciones de dominio.

Se persisten como `varchar` + `CHECK` (convención 3.1 de la especificación), no como
ENUM nativo de PostgreSQL. Los valores de estas clases son la única fuente para los
CHECK de los modelos ORM y de las migraciones.
"""

from enum import StrEnum


class NombreRol(StrEnum):
    """Nombres canónicos de los roles sembrados (`roles.nombre`)."""

    ADMINISTRADOR = "Administrador"
    ENCARGADO_INVENTARIO = "EncargadoInventario"
    ENCARGADO_VENTAS = "EncargadoVentas"
    ENCARGADO_BODEGA = "EncargadoBodega"
    ENCARGADO_COMPRAS = "EncargadoCompras"
    GERENTE = "Gerente"
    PROVEEDOR = "Proveedor"
    LIQUIDADOR = "Liquidador"


class EstadoCarga(StrEnum):
    BORRADOR = "borrador"
    PENDIENTE_APROBACION = "pendiente_aprobacion"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    DESPACHADA = "despachada"


# Estados que ocupan el cupo "una carga vigente por ruta/día".
ESTADOS_CARGA_VIGENTE = (
    EstadoCarga.BORRADOR,
    EstadoCarga.PENDIENTE_APROBACION,
    EstadoCarga.APROBADA,
)


class TipoMovimiento(StrEnum):
    ENTRADA = "entrada"
    SALIDA = "salida"
    AJUSTE = "ajuste"
    RESERVA = "reserva"
    LIBERACION = "liberacion"


class ReferenciaTipo(StrEnum):
    CARGA_RUTA = "carga_ruta"
    PEDIDO = "pedido"
    AJUSTE = "ajuste"
    ETL = "etl"


class TipoAjuste(StrEnum):
    """Modalidad de un ajuste manual de existencias (ADR-16)."""

    INCREMENTO = "incremento"
    DECREMENTO = "decremento"
    FIJAR = "fijar"


class EstadoPedido(StrEnum):
    BORRADOR = "borrador"
    ENVIADO = "enviado"
    CONFIRMADO = "confirmado"
    RECIBIDO = "recibido"
    CANCELADO = "cancelado"


class EstadoLoteEtl(StrEnum):
    RECIBIDO = "recibido"
    VALIDADO = "validado"
    RECHAZADO = "rechazado"
    CARGADO = "cargado"


class OrigenDatos(StrEnum):
    """Procedencia de un lote de `ventas_historicas` (ADR-14)."""

    EXCEL_HISTORICO = "excel_historico"
    LIQUIDACION = "liquidacion"


class EstadoLiquidacion(StrEnum):
    BORRADOR = "borrador"
    CERRADA = "cerrada"
    ANULADA = "anulada"


class FuenteReentrenamiento(StrEnum):
    """Qué datos alimentan un entrenamiento (`ml.fuente_reentrenamiento`, ADR-14)."""

    EXCEL_HISTORICO = "excel_historico"
    EXCEL_MAS_LIQUIDACION = "excel_mas_liquidacion"
    LIQUIDACION = "liquidacion"


class Algoritmo(StrEnum):
    SKLEARN = "sklearn"
    XGBOOST = "xgboost"
    LSTM = "lstm"


class EstadoModelo(StrEnum):
    CANDIDATO = "candidato"
    PRODUCCION = "produccion"
    ARCHIVADO = "archivado"
    DESCARTADO = "descartado"


class MotivoEntrenamiento(StrEnum):
    PROGRAMADO = "programado"
    MANUAL = "manual"
    DEGRADACION = "degradacion"


class TipoEvaluacion(StrEnum):
    HOLDOUT = "holdout"
    BACKTEST = "backtest"
    PRODUCCION = "produccion"


class TipoAlerta(StrEnum):
    STOCK_BAJO = "stock_bajo"
    QUIEBRE_PROYECTADO = "quiebre_proyectado"
    MAPE_UMBRAL = "mape_umbral"
    ETL_ERROR = "etl_error"
    DIFERENCIA_CAJA = "diferencia_caja"


class Severidad(StrEnum):
    INFO = "info"
    ADVERTENCIA = "advertencia"
    CRITICA = "critica"


class EstadoAlerta(StrEnum):
    ABIERTA = "abierta"
    RECONOCIDA = "reconocida"
    RESUELTA = "resuelta"


class TipoJob(StrEnum):
    REENTRENAMIENTO = "reentrenamiento"
    EVALUACION_PRODUCCION = "evaluacion_produccion"
    PRONOSTICO_NOCTURNO = "pronostico_nocturno"


class EstadoJob(StrEnum):
    EN_COLA = "en_cola"
    EN_EJECUCION = "en_ejecucion"
    COMPLETADO = "completado"
    FALLIDO = "fallido"


class NivelBitacora(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class OrigenBitacora(StrEnum):
    """Capa que generó el registro de la bitácora (ADR-15)."""

    HTTP = "http"
    SERVICIO = "servicio"
    WORKER = "worker"


class ResultadoBitacora(StrEnum):
    EXITO = "exito"
    ERROR = "error"


class OperacionBitacora(StrEnum):
    LECTURA = "lectura"
    ESCRITURA = "escritura"


def sql_in(column: str, values) -> str:
    """Construye la expresión `columna IN ('a','b',...)` para un CheckConstraint."""
    quoted = ", ".join(f"'{v.value if isinstance(v, StrEnum) else v}'" for v in values)
    return f"{column} IN ({quoted})"
