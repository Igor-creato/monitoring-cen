# Price Monitoring Backend

MVP backend service for monitoring product prices by URL.

Architecture details live in:

- `BACKEND_ARCHITECTURE_FOR_AGENT.md`
- `MVP_PRICE_MONITORING_SPEC.md`

## Local Run

```bash
cp .env.local.example .env.local
docker compose --env-file .env.local up --build
```

Before the API and worker start, the `migrate` service runs:

```bash
alembic upgrade head
```

API will be available at:

```text
http://localhost:8000
```

## Deployment

Production, backup, VPS, config, and smoke-test commands live in:

- `docs/DEPLOYMENT.md`
