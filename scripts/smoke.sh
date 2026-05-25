#!/usr/bin/env sh
set -eu

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
BASE_URL="${BASE_URL%/}"
SMOKE_RETRIES="${SMOKE_RETRIES:-30}"
SMOKE_DELAY_SECONDS="${SMOKE_DELAY_SECONDS:-2}"

echo "Smoke testing ${BASE_URL}"

fetch() {
  path="$1"
  attempt=0
  until [ "$attempt" -ge "$SMOKE_RETRIES" ]; do
    if curl -fsS "${BASE_URL}${path}" >/tmp/price-monitor-smoke-response; then
      cat /tmp/price-monitor-smoke-response
      rm -f /tmp/price-monitor-smoke-response
      return 0
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -lt "$SMOKE_RETRIES" ]; then
      sleep "$SMOKE_DELAY_SECONDS"
    fi
  done
  rm -f /tmp/price-monitor-smoke-response
  echo "Smoke check failed for ${BASE_URL}${path} after ${SMOKE_RETRIES} attempts." >&2
  return 1
}

fetch_contains() {
  path="$1"
  pattern="$2"
  fetch "$path" | grep -q "$pattern"
}

fetch "/health" >/dev/null
echo "health ok"

fetch "/ready" >/dev/null
echo "ready ok"

fetch "/login" >/dev/null
echo "login page ok"

fetch_contains "/static/app.css" ".app-shell"
echo "styles ok"

fetch_contains "/static/app.js" "data-loading"
echo "scripts ok"

if fetch "/metrics" >/dev/null 2>&1; then
  echo "metrics ok"
else
  echo "metrics skipped"
fi
