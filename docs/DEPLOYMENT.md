# Deployment

## Local

```bash
cp .env.local.example .env.local
docker compose --env-file .env.local up --build
```

API: `http://localhost:8000`

Run migrations manually:

```bash
docker compose --env-file .env.local run --rm migrate
```

Run smoke tests:

```bash
sh ./scripts/smoke.sh http://localhost:8000
```

Use the real Wildberries provider locally:

```bash
cp .env.local.example .env.local
# edit .env.local:
# PRODUCT_FETCH_PROVIDER=wildberries_direct
# WILDBERRIES_PROXY_URL=<optional-proxy-url>
docker compose --env-file .env.local up --build
```

After registration at `http://localhost:8000`, add a Wildberries product URL. The worker
checks due monitors automatically every minute. To force a check, set `INTERNAL_API_TOKEN`
in `.env.local` and call:

```bash
curl -X POST \
  -H "X-Internal-Token: $INTERNAL_API_TOKEN" \
  http://localhost:8000/internal/check-monitor/<monitor_id>
```

The legacy Apify adapter remains available with `PRODUCT_FETCH_PROVIDER=apify`,
but Wildberries monitoring should use `wildberries_direct` by default.

## Production

Prepare VPS:

- Ubuntu LTS with Docker Engine and Docker Compose plugin.
- Open inbound SSH port, `80`, and `443`. If SSH is not on `22`, set `VPS_PORT`.
- Keep MariaDB and Redis private; do not expose `3306` or `6379`.
- Minimum: 1 vCPU, 2 GB RAM, 20 GB SSD.
- Recommended: 2 vCPU, 4 GB RAM, 40 GB SSD.

First-time bootstrap on the VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/Igor-creato/monitoring-cen/master/scripts/bootstrap-vps.sh -o /tmp/bootstrap-vps.sh
sh /tmp/bootstrap-vps.sh
```

The script asks for:

- application domain (`APP_DOMAIN`), for example `monitor.example.com`;
- Let's Encrypt email (`LETSENCRYPT_EMAIL`);
- admin email list (`ADMIN_EMAILS`);
- SMTP host, port, username, password, sender email, and STARTTLS flag.
- whether to use an existing Traefik on the server.

It clones the repository to `$HOME/price-monitor` by default, writes `.env.prod`
with generated secrets, starts the Docker Compose production stack, and runs the
smoke test against `https://$APP_DOMAIN`.

If another Traefik already owns ports `80` and `443`, answer `true` for existing
Traefik and enter the Docker network used by that Traefik. Find it with:

```bash
docker network ls
docker inspect <traefik-container-name> --format '{{json .NetworkSettings.Networks}}'
```

The app will not start its own Traefik in this mode. It will attach the API
container to the existing Traefik network and expose Traefik labels for
`APP_DOMAIN`.

If this is a fresh server with no Traefik, answer `false`. The bundled Traefik
profile will bind `80` and `443`.

Optional bootstrap overrides:

```bash
APP_DIR=/home/igor/price-monitor \
REPO_URL=git@github.com:Igor-creato/monitoring-cen.git \
BRANCH=master \
sh /tmp/bootstrap-vps.sh
```

Configure GitHub repository secrets after bootstrap:

- `VPS_HOST`: VPS IP address or hostname.
- `VPS_PORT`: SSH port, for example `56789`.
- `VPS_USER`: SSH user that can access `VPS_APP_DIR` and run Docker Compose.
- `VPS_SSH_KEY`: private SSH key for `VPS_USER`.
- `VPS_APP_DIR`: full app path, for example `/home/igor/price-monitor`.

Automatic deploys run from the `master` branch after CI, Docker builds, and image
scans pass.

Manual deploy:

```bash
cd /home/igor/price-monitor
git pull --ff-only origin master
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
sh ./scripts/smoke.sh "https://$APP_DOMAIN"
```

Logs:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker
```

Rollback:

```bash
cd /home/igor/price-monitor
git checkout <previous-known-good-sha>
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
sh ./scripts/smoke.sh "https://$APP_DOMAIN"
git checkout master
```

Note: local AGENTS instructions prefer `rtk`-prefixed commands, but `rtk` is not
available in the current local environment. The documented server commands use
plain `git`, `docker`, `curl`, and `sh` so a fresh VPS does not depend on `rtk`.

## Configs

- `local`: `.env.local`, bind-mounted backend from `docker-compose.override.yml`, exposed local ports `8000`, `3306`, `6379`, `PRODUCT_FETCH_PROVIDER=mock`.
- `stage`: `.env.stage`, Traefik on a stage domain, separate MariaDB volume and stage secrets.
- `prod`: `.env.prod`, Traefik HTTPS, no DB/Redis public ports, `PRODUCT_FETCH_PROVIDER=wildberries_direct`.

Keep real env files out of git. Example files contain placeholders only.

## Backups

Create backup directory:

```bash
mkdir -p /home/igor/price-monitor/backups
```

Backup:

```bash
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T mariadb \
  sh -c 'mariadb-dump -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" --single-transaction --routines --triggers "$MARIADB_DATABASE"' \
  | gzip > "/home/igor/price-monitor/backups/price-monitor_$(date +%F_%H-%M-%S).sql.gz"
```

Restore drill:

```bash
gunzip -c /home/igor/price-monitor/backups/<backup>.sql.gz | docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T mariadb \
  sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"'
```

Recommended policy:

- Run the backup command daily from cron or a systemd timer.
- Keep 14 days locally.
- Copy backups offsite with `rclone` or `restic`.
- Test restore monthly.
