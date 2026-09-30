FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: runtime OpenMP requerido por XGBoost; curl: healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Capa de dependencias (se cachea mientras pyproject.toml no cambie).
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install ".[dev]" \
    && rm -rf app build *.egg-info

COPY . .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/ml_artifacts /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
