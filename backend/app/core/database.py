"""Engine y fábrica de sesiones de SQLAlchemy.

El engine se crea de forma perezosa para que importar la app (p. ej. al exportar
el contrato OpenAPI) no requiera una base de datos disponible.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().sqlalchemy_database_uri, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
