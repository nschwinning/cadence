#!/usr/bin/env bash
#
# Manually trigger the AI portfolio's daily rebalance against a backend running
# on the host (see scripts/dev-host.sh). This is the host-dev equivalent of the
# Docker `cron` sidecar, which cannot reach a host backend.
#
# The rebalance endpoint is guarded by the X-Cron-Token shared secret.
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8002}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Read REBALANCE_CRON_TOKEN from the root .env unless already in the environment.
# The root .env is docker-compose format (unquoted spaces), so parse it safely
# rather than shell `source`-ing it.
if [ -z "${REBALANCE_CRON_TOKEN:-}" ] && [ -f .env ]; then
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
  done < .env
fi
if [ -z "${REBALANCE_CRON_TOKEN:-}" ]; then
  echo "REBALANCE_CRON_TOKEN is empty; set it in .env so the rebalance trigger is accepted." >&2
  exit 1
fi

B="http://localhost:${BACKEND_PORT}/api/v1"

echo "==> Triggering daily rebalance..."
curl -fsS -X POST -H "X-Cron-Token: ${REBALANCE_CRON_TOKEN}" "$B/ai-portfolio/rebalance-daily" >/dev/null
echo "==> Daily rebalance triggered."
