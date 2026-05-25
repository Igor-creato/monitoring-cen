FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
ENV PYTHONPATH=/app/backend

COPY pyproject.toml /app/pyproject.toml
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY backend /app/backend
RUN pip install --upgrade pip && pip install /app

RUN useradd --create-home --uid 1001 appuser \
    && chown -R appuser:appuser /app

USER appuser

CMD ["arq", "app.workers.arq_settings.WorkerSettings"]
