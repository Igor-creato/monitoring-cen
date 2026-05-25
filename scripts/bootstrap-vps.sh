#!/usr/bin/env sh
set -eu

DEFAULT_APP_DIR="${HOME:-$(pwd -P)}/price-monitor"
APP_DIR="${APP_DIR:-$DEFAULT_APP_DIR}"
REPO_URL="${REPO_URL:-https://github.com/Igor-creato/monitoring-cen.git}"
BRANCH="${BRANCH:-master}"

case "$APP_DIR" in
    /*) ;;
    *) APP_DIR="$(pwd -P)/$APP_DIR" ;;
esac

prompt_required() {
    label="$1"
    value=""
    while [ -z "$value" ]; do
        printf "%s: " "$label" >&2
        IFS= read -r value
        if [ -z "$value" ]; then
            echo "Value is required." >&2
        fi
    done
    printf "%s" "$value"
}

prompt_default() {
    label="$1"
    default="$2"
    printf "%s [%s]: " "$label" "$default" >&2
    IFS= read -r value
    if [ -z "$value" ]; then
        value="$default"
    fi
    printf "%s" "$value"
}

prompt_secret() {
    label="$1"
    value=""
    while [ -z "$value" ]; do
        printf "%s: " "$label" >&2
        stty -echo 2>/dev/null || true
        IFS= read -r value
        stty echo 2>/dev/null || true
        printf "\n" >&2
        if [ -z "$value" ]; then
            echo "Value is required." >&2
        fi
    done
    printf "%s" "$value"
}

prompt_bool() {
    label="$1"
    default="$2"
    value=""
    while [ -z "$value" ]; do
        printf "%s [%s]: " "$label" "$default" >&2
        IFS= read -r value
        if [ -z "$value" ]; then
            value="$default"
        fi
        case "$value" in
            true|false) ;;
            y|Y|yes|YES|Yes) value="true" ;;
            n|N|no|NO|No) value="false" ;;
            *)
                echo "Enter true or false." >&2
                value=""
                ;;
        esac
    done
    printf "%s" "$value"
}

random_hex() {
    bytes="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$bytes"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import secrets; print(secrets.token_hex($bytes))"
    else
        echo "openssl or python3 is required to generate secrets." >&2
        exit 1
    fi
}

random_fernet_key() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    else
        echo "python3 is required to generate ADMIN_SECRETS_KEY." >&2
        exit 1
    fi
}

random_password() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import secrets; print(secrets.token_urlsafe(24))"
    elif command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 24 | tr '+/' '-_' | tr -d '='
    else
        echo "openssl or python3 is required to generate admin password." >&2
        exit 1
    fi
}

first_csv_item() {
    python3 - "$1" <<'PY'
import sys

for item in sys.argv[1].split(","):
    item = item.strip()
    if item:
        print(item)
        raise SystemExit(0)

raise SystemExit(1)
PY
}

require_command() {
    command_name="$1"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "$command_name is required. Install it and run this script again." >&2
        exit 1
    fi
}

bootstrap_admin() {
    docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml $COMPOSE_PROFILES exec \
        -T \
        -e PRIMARY_ADMIN_EMAIL="$PRIMARY_ADMIN_EMAIL" \
        -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
        api \
        python - <<'PY'
import asyncio
import os

from sqlalchemy import select

from app.domain.enums import UserRole, UserStatus
from app.infra.config import get_settings
from app.infra.db.models.user import UserModel
from app.infra.db.session import async_session_factory
from app.infra.security import hash_password


async def main() -> None:
    email = os.environ["PRIMARY_ADMIN_EMAIL"].strip().lower()
    password = os.environ["ADMIN_PASSWORD"]
    settings = get_settings()

    async with async_session_factory() as session:
        result = await session.execute(select(UserModel).where(UserModel.email == email))
        user = result.scalar_one_or_none()
        password_hash = hash_password(password, settings)

        if user is None:
            session.add(
                UserModel(
                    email=email,
                    password_hash=password_hash,
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                )
            )
        else:
            user.password_hash = password_hash
            user.role = UserRole.ADMIN
            user.status = UserStatus.ACTIVE

        await session.commit()


asyncio.run(main())
PY
}

write_env() {
    env_file="$1"

    cat > "$env_file" <<EOF
APP_ENV=prod
APP_ENV_FILE=.env.prod
APP_DEBUG=false
APP_NAME=price-monitor
APP_DOMAIN=$APP_DOMAIN
COMPOSE_PROFILES=$COMPOSE_PROFILES_VALUE
LETSENCRYPT_EMAIL=$LETSENCRYPT_EMAIL
TRAEFIK_PUBLIC_NETWORK=$TRAEFIK_PUBLIC_NETWORK
TRAEFIK_PUBLIC_NETWORK_EXTERNAL=$TRAEFIK_PUBLIC_NETWORK_EXTERNAL
TRAEFIK_ENTRYPOINT=$TRAEFIK_ENTRYPOINT
TRAEFIK_CERT_RESOLVER=$TRAEFIK_CERT_RESOLVER

MARIADB_DATABASE=price_monitor
MARIADB_USER=price_monitor
MARIADB_PASSWORD=$MARIADB_PASSWORD
MARIADB_ROOT_PASSWORD=$MARIADB_ROOT_PASSWORD
DATABASE_URL=mysql+asyncmy://price_monitor:$MARIADB_PASSWORD@mariadb:3306/price_monitor?charset=utf8mb4
REDIS_URL=redis://redis:6379/0

JWT_SECRET_KEY=$JWT_SECRET_KEY
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_HASH_ITERATIONS=260000
INTERNAL_API_TOKEN=$INTERNAL_API_TOKEN
ADMIN_EMAILS=$ADMIN_EMAILS
ADMIN_SECRETS_KEY=$ADMIN_SECRETS_KEY

HTTP_TIMEOUT_SECONDS=15
HTTP_MAX_CONNECTIONS=100

PRODUCT_FETCH_PROVIDER=wildberries_direct
PRODUCT_FETCH_REQUEST_TIMEOUT_SECONDS=60
PRODUCT_FETCH_RETRY_MAX_ATTEMPTS=3
PRODUCT_FETCH_RETRY_BASE_DELAY_SECONDS=0.25
PRODUCT_FETCH_RETRY_MAX_DELAY_SECONDS=5
PRODUCT_FETCH_RETRY_JITTER_RATIO=0.2

WILDBERRIES_PROXY_URL=
WILDBERRIES_DEST=-1257786
WILDBERRIES_REQUEST_TIMEOUT_SECONDS=60
WILDBERRIES_BASKET_MAX_HOST=20

APIFY_API_TOKEN=
APIFY_ACTOR_ID=
APIFY_BASE_URL=https://api.apify.com

ZYTE_API_KEY=
ZYTE_API_URL=https://api.zyte.com/v1/extract

CHECK_DEFAULT_INTERVAL_SECONDS=3600
CHECK_BATCH_SIZE=100
CHECK_MAX_RETRIES=3
CHECK_LOCK_TTL_SECONDS=180
CHECK_LOCK_RETRY_DELAY_SECONDS=60
CHECK_SCHEDULER_TICK_SECONDS=60
DEAD_LETTER_MAX_ITEMS=1000

NOTIFICATION_DEDUPE_WINDOW_SECONDS=86400
NOTIFICATION_MAX_RETRIES=3
NOTIFICATION_RETRY_BASE_DELAY_SECONDS=30
NOTIFICATION_RETRY_MAX_DELAY_SECONDS=300

TELEGRAM_BOT_TOKEN=
EMAIL_SMTP_HOST=$EMAIL_SMTP_HOST
EMAIL_SMTP_PORT=$EMAIL_SMTP_PORT
EMAIL_SMTP_USER=$EMAIL_SMTP_USER
EMAIL_SMTP_PASSWORD=$EMAIL_SMTP_PASSWORD
EMAIL_SMTP_FROM=$EMAIL_SMTP_FROM
EMAIL_SMTP_USE_TLS=$EMAIL_SMTP_USE_TLS

LOG_LEVEL=INFO
EOF

    chmod 600 "$env_file"
}

echo "Price Monitor VPS bootstrap"
echo "Repository: $REPO_URL"
echo "Target directory: $APP_DIR"
echo

require_command git
require_command docker
require_command python3

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required. Install it and run this script again." >&2
    exit 1
fi

APP_DOMAIN="$(prompt_required "Application domain, for example monitor.example.com")"
LETSENCRYPT_EMAIL="$(prompt_required "Let's Encrypt email")"
ADMIN_EMAILS="$(prompt_default "Admin email list, comma-separated" "$LETSENCRYPT_EMAIL")"
PRIMARY_ADMIN_EMAIL="$(first_csv_item "$ADMIN_EMAILS")"

EMAIL_SMTP_HOST="$(prompt_required "SMTP host")"
EMAIL_SMTP_PORT="$(prompt_default "SMTP port" "587")"
EMAIL_SMTP_USER="$(prompt_required "SMTP username")"
EMAIL_SMTP_PASSWORD="$(prompt_secret "SMTP password")"
EMAIL_SMTP_FROM="$(prompt_default "SMTP from email" "$EMAIL_SMTP_USER")"
EMAIL_SMTP_USE_TLS="$(prompt_default "Use SMTP STARTTLS? true/false" "true")"
USE_EXISTING_TRAEFIK="$(prompt_bool "Use an existing Traefik on this server? true/false" "true")"

if [ "$USE_EXISTING_TRAEFIK" = "true" ]; then
    TRAEFIK_PUBLIC_NETWORK="$(prompt_required "Existing Traefik Docker network name")"
    TRAEFIK_PUBLIC_NETWORK_EXTERNAL="true"
    TRAEFIK_ENTRYPOINT="$(prompt_default "Traefik HTTPS entrypoint" "websecure")"
    TRAEFIK_CERT_RESOLVER="$(prompt_default "Traefik certificate resolver" "letsencrypt")"
    COMPOSE_PROFILES_VALUE=""
    COMPOSE_PROFILES=""
else
    TRAEFIK_PUBLIC_NETWORK="$(prompt_default "Bundled Traefik Docker network name" "price-monitor-public")"
    TRAEFIK_PUBLIC_NETWORK_EXTERNAL="false"
    TRAEFIK_ENTRYPOINT="websecure"
    TRAEFIK_CERT_RESOLVER="letsencrypt"
    COMPOSE_PROFILES_VALUE="bundled-traefik"
    COMPOSE_PROFILES="--profile bundled-traefik"
fi

MARIADB_PASSWORD="$(random_hex 24)"
MARIADB_ROOT_PASSWORD="$(random_hex 24)"
JWT_SECRET_KEY="$(random_hex 32)"
INTERNAL_API_TOKEN="$(random_hex 32)"
ADMIN_SECRETS_KEY="$(random_fernet_key)"
ADMIN_PASSWORD="$(random_password)"

if [ ! -d "$APP_DIR/.git" ]; then
    parent_dir="$(dirname "$APP_DIR")"
    if [ ! -d "$parent_dir" ]; then
        mkdir -p "$parent_dir" 2>/dev/null || {
            echo "Cannot create $parent_dir. Run this script as a user with access to $parent_dir." >&2
            exit 1
        }
    fi
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ -f .env.prod ]; then
    backup_file=".env.prod.$(date +%Y%m%d%H%M%S).bak"
    cp .env.prod "$backup_file"
    chmod 600 "$backup_file"
    echo "Existing .env.prod backed up to $backup_file"
fi

write_env ".env.prod"

docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml $COMPOSE_PROFILES up -d --build --remove-orphans
bootstrap_admin
sh ./scripts/smoke.sh "https://$APP_DOMAIN"

echo
echo "Bootstrap complete."
echo "Admin login: $PRIMARY_ADMIN_EMAIL"
echo "Admin password: $ADMIN_PASSWORD"
echo "Set these GitHub repository secrets for automatic deploys:"
echo "VPS_HOST, VPS_PORT, VPS_USER, VPS_SSH_KEY, VPS_APP_DIR=$APP_DIR"
