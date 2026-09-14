#!/usr/bin/env bash
#
# Start the Cadence dev stack for a host behind a TLS-inspecting proxy (Zscaler).
#
# Postgres runs in Docker; the Python backend and the Vite frontend run directly
# on the host so their outbound HTTPS (OpenAI, SerpAPI, Alpaca) is verified
# against the OS trust store, which trusts the corporate inspection CA. See
# backend/src/cadence/_tls.py for why the backend must not run in a container here.
#
#   Postgres : Docker, exposed on localhost:${DB_PORT}
#   Backend  : host,   http://localhost:${BACKEND_PORT}
#   Frontend : host,   http://localhost:5174 (proxies /api -> backend)
#
# Ctrl+C stops the host backend and frontend; the Postgres container is left
# running (it holds your data). Stop it with: docker compose stop db
set -euo pipefail

DB_PORT="${DB_PORT:-5435}"
BACKEND_PORT="${BACKEND_PORT:-8002}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Safe dotenv loader: the root .env is in docker-compose format (values may be
# unquoted and contain spaces, e.g. the cron schedule), so it must NOT be shell
# `source`d. Split on the first '=', export the value literally, strip optional
# surrounding quotes; skip blanks and comments.
load_dotenv() {
  local f="$1" line key val
  [ -f "$f" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    [ "${line#*=}" = "$line" ] && continue
    key="${line%%=*}"; val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
    case "$val" in
      \"*\") val="${val#\"}"; val="${val%\"}" ;;
      \'*\') val="${val#\'}"; val="${val%\'}" ;;
    esac
    export "$key=$val"
  done < "$f"
}

# Load secrets (OPENAI_API_KEY, SERP_API_KEY, ALPACA_*, REBALANCE_CRON_TOKEN, ...)
# from the root .env. The backend runs with CWD=backend/, where pydantic-settings
# would otherwise find no .env. Real env vars take precedence over the .env file,
# so the DATABASE_URL override below still wins.
load_dotenv .env

# Host processes talk to Postgres via the mapped port, not the Docker-internal
# "db" hostname baked into .env. This override wins over the .env value.
export DATABASE_URL="postgresql+psycopg://cadence:cadence@localhost:${DB_PORT}/cadence"

pids=()
cleanup() {
  echo ""
  echo "==> Shutting down host processes (Postgres container left running)..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "==> Starting Postgres (Docker)..."
docker compose up -d db

echo "==> Waiting for Postgres to be healthy on localhost:${DB_PORT}..."
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U cadence -d cadence >/dev/null 2>&1; then
    echo "    Postgres is ready."
    break
  fi
  sleep 1
done

echo "==> Applying database migrations (Alembic)..."
(cd backend && uv run alembic upgrade head)

echo "==> Installing frontend dependencies (if needed)..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

echo "==> Starting backend on http://localhost:${BACKEND_PORT} ..."
(cd backend && uv run uvicorn cadence.api.app:app --reload --port "${BACKEND_PORT}") &
pids+=($!)

echo "==> Starting frontend on http://localhost:5174 ..."
(cd frontend && VITE_PROXY_TARGET="http://localhost:${BACKEND_PORT}" npm run dev) &
pids+=($!)

echo ""
echo "==> Cadence dev stack is up. Press Ctrl+C to stop."
wait
