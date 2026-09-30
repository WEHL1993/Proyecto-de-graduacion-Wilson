"""Configuración de la aplicación a partir de variables de entorno (.env)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "API Análisis Predictivo — Desarrollos Comerciales del Sur, S.A."
    app_version: str = "1.0.0"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"

    # PostgreSQL
    postgres_user: str = "ds_user"
    postgres_password: str = "ds_password"
    postgres_db: str = "ds_predictive"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # Si se define, tiene prioridad sobre los componentes anteriores.
    database_url: str | None = None

    # Seguridad (JWT)
    jwt_secret_key: str = Field(default="cambiar-en-produccion", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CORS (frontend en fase posterior)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Rutas de artefactos y datos
    ml_artifacts_dir: Path = PROJECT_ROOT / "ml_artifacts"
    data_dir: Path = PROJECT_ROOT / "data"

    # Worker predictivo (ADR-04): sondeo de la cola `jobs_ml` y cadencia de la evaluación
    worker_poll_segundos: int = Field(default=15, ge=1)
    worker_evaluacion_intervalo_segundos: int = Field(default=6 * 3600, ge=60)

    # ML: familia lógica (`modelos_ml.nombre`) que atiende /predictions/demand
    ml_modelo_nombre: str = "demanda_diaria"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _cors_origins_desde_csv(cls, value: object) -> object:
        """Permite `CORS_ORIGINS=http://a,http://b` como variable de entorno plana."""
        if isinstance(value, str):
            return [origen.strip() for origen in value.split(",") if origen.strip()]
        return value

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
