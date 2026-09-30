"""Enumeraciones de dominio.

Se persisten como `varchar` + `CHECK` (convención 3.1 de la especificación), no como
ENUM nativo de PostgreSQL. Los valores de estas clases son la única fuente para los
CHECK de los modelos ORM y de las migraciones.
"""

from enum import StrEnum


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


def sql_in(column: str, values) -> str:
    """Construye la expresión `columna IN ('a','b',...)` para un CheckConstraint."""
    quoted = ", ".join(f"'{v.value if isinstance(v, StrEnum) else v}'" for v in values)
    return f"{column} IN ({quoted})"
