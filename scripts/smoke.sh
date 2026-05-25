#!/usr/bin/env sh
set -eu

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
BASE_URL="${BASE_URL%/}"

echo "Smoke testing ${BASE_URL}"

curl -fsS "${BASE_URL}/health" >/dev/null
echo "health ok"

curl -fsS "${BASE_URL}/ready" >/dev/null
echo "ready ok"

curl -fsS "${BASE_URL}/login" >/dev/null
echo "login page ok"

curl -fsS "${BASE_URL}/static/app.css" | grep -q ".app-shell"
echo "styles ok"

curl -fsS "${BASE_URL}/static/app.js" | grep -q "data-loading"
echo "scripts ok"

if curl -fsS "${BASE_URL}/metrics" >/dev/null 2>&1; then
  echo "metrics ok"
else
  echo "metrics skipped"
fi
