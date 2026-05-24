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

## Real Wildberries Monitoring

Local config uses `PRODUCT_FETCH_PROVIDER=mock` by default. To check real product pages:

1. Copy `.env.local.example` to `.env.local`.
2. Set `PRODUCT_FETCH_PROVIDER=apify`.
3. Fill `APIFY_API_TOKEN` and `APIFY_ACTOR_ID`.
4. Optionally set `INTERNAL_API_TOKEN` if you want to run manual checks through the internal API.
5. Start the stack:

```bash
docker compose --env-file .env.local up --build
```

Open `http://localhost:8000`, register, and add a Wildberries product URL. The worker
claims due monitors every minute. For a manual check, use the created monitor id:

```bash
curl -X POST \
  -H "X-Internal-Token: $INTERNAL_API_TOKEN" \
  http://localhost:8000/internal/check-monitor/<monitor_id>
```

The production Apify adapter currently supports Wildberries only.

## Admin UI

Set `ADMIN_EMAILS` to a comma-separated list before registration or login. Matching
users are promoted to the `admin` role and can open:

```text
http://localhost:8000/admin
```

To save provider/internal tokens from the admin UI, set `ADMIN_SECRETS_KEY` to a
Fernet key. You can generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Runtime token overrides saved in the admin UI are encrypted in the database and
take precedence over env values. Env values remain the fallback.

## Deployment

Production, backup, VPS, config, and smoke-test commands live in:

- `docs/DEPLOYMENT.md`
