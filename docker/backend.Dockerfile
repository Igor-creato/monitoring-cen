FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ENV PYTHONPATH=/app/backend

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir /app

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY backend /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
