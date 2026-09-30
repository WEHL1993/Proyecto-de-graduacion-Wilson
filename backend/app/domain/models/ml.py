"""ML y pronósticos: registro de modelos, métricas, pronósticos, alertas y jobs (sección 3.4)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    Algoritmo,
    EstadoAlerta,
    EstadoJob,
    EstadoModelo,
    MotivoEntrenamiento,
    Severidad,
    TipoAlerta,
    TipoEvaluacion,
    TipoJob,
    sql_in,
)
from app.domain.models.base import Base, Cantidad, PorcentajeError, UUIDPkMixin


class ModeloML(UUIDPkMixin, Base):
    __tablename__ = "modelos_ml"
    __table_args__ = (
        UniqueConstraint("nombre", "version"),
        CheckConstraint(sql_in("algoritmo", Algoritmo), name="algoritmo_valido"),
        CheckConstraint(sql_in("estado", EstadoModelo), name="estado_valido"),
        CheckConstraint(sql_in("motivo_entrenamiento", MotivoEntrenamiento), name="motivo_valido"),
        CheckConstraint("ventana_desde < ventana_hasta", name="ventana_coherente"),
        CheckConstraint(
            "estado <> 'produccion' OR promovido_en IS NOT NULL", name="produccion_promovido"
        ),
        # ADR-03: un único modelo en producción por familia lógica.
        Index(
            "uq_modelos_ml_produccion_nombre",
            "nombre",
            unique=True,
            postgresql_where=text("estado = 'produccion'"),
        ),
    )

    nombre: Mapped[str] = mapped_column(String(80))
    algoritmo: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(
        String(15), server_default=text(f"'{EstadoModelo.CANDIDATO}'")
    )
    ruta_artefacto: Mapped[str] = mapped_column(String(255))
    hash_artefacto: Mapped[str] = mapped_column(CHAR(64))
    hiperparametros: Mapped[dict] = mapped_column(JSONB)
    esquema_features: Mapped[dict | list] = mapped_column(JSONB)
    ventana_desde: Mapped[date] = mapped_column(Date)
    ventana_hasta: Mapped[date] = mapped_column(Date)
    motivo_entrenamiento: Mapped[str] = mapped_column(String(15))
    # NULL cuando lo entrena el Worker.
    entrenado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    entrenado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    promovido_en: Mapped[datetime | None]


class MetricaEvaluacion(UUIDPkMixin, Base):
    __tablename__ = "metricas_evaluacion"
    __table_args__ = (
        CheckConstraint(sql_in("tipo_evaluacion", TipoEvaluacion), name="tipo_valido"),
        CheckConstraint("mae >= 0 AND rmse >= 0", name="errores_no_negativos"),
        CheckConstraint("mape IS NULL OR mape >= 0", name="mape_no_negativo"),
        CheckConstraint("n_muestras > 0", name="n_muestras_positivo"),
        CheckConstraint("periodo_desde <= periodo_hasta", name="periodo_coherente"),
        # Serie de degradación por modelo.
        Index(
            "ix_metricas_evaluacion_modelo_tipo_periodo",
            "modelo_id",
            "tipo_evaluacion",
            text("periodo_hasta DESC"),
        ),
    )

    modelo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modelos_ml.id", ondelete="RESTRICT"))
    # NULL = métrica global del modelo.
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    tipo_evaluacion: Mapped[str] = mapped_column(String(12))
    mae: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    rmse: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    # NULL si la demanda real es 0 en todo el periodo (evita división por cero silenciosa).
    mape: Mapped[PorcentajeError | None]
    n_muestras: Mapped[int] = mapped_column(Integer)
    periodo_desde: Mapped[date] = mapped_column(Date)
    periodo_hasta: Mapped[date] = mapped_column(Date)
    supera_umbral: Mapped[bool] = mapped_column(Boolean, server_default=false())
    evaluado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class PronosticoDemanda(Base):
    __tablename__ = "pronosticos_demanda"
    __table_args__ = (
        # ruta_id NULL = demanda agregada; NULLS NOT DISTINCT evita duplicados del agregado.
        UniqueConstraint(
            "modelo_id",
            "producto_id",
            "ruta_id",
            "fecha_objetivo",
            "horizonte_dias",
            name="uq_pronosticos_demanda_clave",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("horizonte_dias BETWEEN 1 AND 30", name="horizonte_rango"),
        CheckConstraint("demanda_predicha >= 0", name="predicha_no_negativa"),
        CheckConstraint("demanda_real IS NULL OR demanda_real >= 0", name="real_no_negativa"),
        CheckConstraint(
            "(limite_inferior IS NULL OR limite_inferior <= demanda_predicha) "
            "AND (limite_superior IS NULL OR demanda_predicha <= limite_superior)",
            name="intervalo_coherente",
        ),
        Index("ix_pronosticos_demanda_fecha_producto", "fecha_objetivo", "producto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    modelo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modelos_ml.id", ondelete="RESTRICT"))
    producto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("productos.id", ondelete="RESTRICT"))
    ruta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rutas.id", ondelete="RESTRICT"), index=True
    )
    fecha_objetivo: Mapped[date] = mapped_column(Date)
    horizonte_dias: Mapped[int] = mapped_column(Integer)
    demanda_predicha: Mapped[Cantidad]
    limite_inferior: Mapped[Cantidad | None]
    limite_superior: Mapped[Cantidad | None]
    demanda_real: Mapped[Cantidad | None]
    generado_en: Mapped[datetime] = mapped_column(server_default=func.now())


class Alerta(UUIDPkMixin, Base):
    __tablename__ = "alertas"
    __table_args__ = (
        CheckConstraint(sql_in("tipo", TipoAlerta), name="tipo_valido"),
        CheckConstraint(sql_in("severidad", Severidad), name="severidad_valida"),
        CheckConstraint(sql_in("estado", EstadoAlerta), name="estado_valido"),
        CheckConstraint(
            "estado <> 'resuelta' OR resuelta_en IS NOT NULL", name="resolucion_fechada"
        ),
        # Bandeja de alertas.
        Index(
            "ix_alertas_estado_severidad_creada",
            "estado",
            "severidad",
            text("creada_en DESC"),
        ),
    )

    tipo: Mapped[str] = mapped_column(String(25))
    severidad: Mapped[str] = mapped_column(String(12))
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("productos.id", ondelete="RESTRICT"), index=True
    )
    modelo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modelos_ml.id", ondelete="RESTRICT"), index=True
    )
    mensaje: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(
        String(12), server_default=text(f"'{EstadoAlerta.ABIERTA}'")
    )
    creada_en: Mapped[datetime] = mapped_column(server_default=func.now())
    resuelta_en: Mapped[datetime | None]


class ParametroSistema(Base):
    """Umbrales configurables (p. ej. `ml.mape_umbral`, `ml.periodos_consecutivos`), ADR-08."""

    __tablename__ = "parametros_sistema"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[dict | list | str | int | float | bool] = mapped_column(JSONB)
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    actualizado_en: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class JobML(UUIDPkMixin, Base):
    """Seguimiento de reentrenamientos y jobs asíncronos del Worker (ADR-04)."""

    __tablename__ = "jobs_ml"
    __table_args__ = (
        CheckConstraint(sql_in("tipo", TipoJob), name="tipo_valido"),
        CheckConstraint(sql_in("estado", EstadoJob), name="estado_valido"),
        CheckConstraint(
            "finalizado_en IS NULL OR iniciado_en IS NULL OR finalizado_en >= iniciado_en",
            name="tiempos_coherentes",
        ),
        # Cola del Worker: toma los jobs pendientes más antiguos.
        Index("ix_jobs_ml_estado_solicitado", "estado", "solicitado_en"),
    )

    tipo: Mapped[str] = mapped_column(String(25))
    estado: Mapped[str] = mapped_column(String(15), server_default=text(f"'{EstadoJob.EN_COLA}'"))
    parametros: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    solicitado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    resultado_modelo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("modelos_ml.id", ondelete="SET NULL")
    )
    solicitado_en: Mapped[datetime] = mapped_column(server_default=func.now())
    iniciado_en: Mapped[datetime | None]
    finalizado_en: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(Text)
