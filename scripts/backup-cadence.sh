#!/usr/bin/env bash
#
# Off-host backup of the Cadence stack to pCloud, reusing the existing `pcloud:`
# rclone remote already configured on the Pi (the same one the paperless-ngx
# backup uses). Dumps both databases on the shared Postgres instance — `cadence`
# (the app) and `litellm` (the proxy's usage/cost logs) — in pg_restore's custom
# format, plus a tar of the deployment configuration (docker-compose.yml + .env).
#
# Everything is staged and validated locally, uploaded under a temporary name,
# verified, then published atomically, so pCloud never holds a half-written
# backup. The upload+verify step is retried (pCloud's listing is eventually
# consistent, so a just-uploaded large dump can briefly fail verification), stale
# `.partial` dirs from earlier failed runs are swept, and any failure sends a
# Pushover alert. Only the newest KEEP_BACKUPS backups are retained.
#
# Install on the Pi (the deploy dir is a git checkout, so a pull delivers this
# file), make it executable, and add a crontab entry that runs it a little before
# the paperless backup:
#
#   chmod +x /home/nils/apps/cadence/scripts/backup-cadence.sh
#   crontab -e   # add:
#   15 2 * * * /usr/bin/flock -n /tmp/cadence-backup.lock /home/nils/apps/cadence/scripts/backup-cadence.sh >> /home/nils/apps/cadence/backup-cadence.log 2>&1
#
# Restore (on the Pi, from a downloaded backup dir):
#   docker compose exec -T db pg_restore -U cadence -d cadence --clean --if-exists < database-cadence.dump
#   docker compose exec -T db pg_restore -U cadence -d litellm --clean --if-exists < database-litellm.dump

set -Eeuo pipefail

# The deploy dir is the parent of this script's scripts/ directory. `docker
# compose` is run from here so it picks up docker-compose.yml and .env.
readonly CADENCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REMOTE_ROOT="pcloud:cadence-backups"
readonly KEEP_BACKUPS=5
readonly UPLOAD_ATTEMPTS=3
readonly VERIFY_SETTLE_SECONDS=10
readonly BACKUP_NAME="cadence-$(date '+%Y-%m-%d_%H-%M-%S')"
readonly REMOTE_PARTIAL="${REMOTE_ROOT}/.${BACKUP_NAME}.partial"

umask 077
export PATH="/usr/local/bin:/usr/bin:/bin"

work_dir="$(mktemp -d "/tmp/${BACKUP_NAME}.XXXXXX")"
backup_dir="${work_dir}/${BACKUP_NAME}"

cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

# Pushover credentials are read from the deploy .env (same ones the app uses) so a
# failed night pings instead of sitting silently in the log. Absent creds or a
# missing curl simply disable the alert; they never fail the backup.
PUSHOVER_USER=""
PUSHOVER_TOKEN=""
if [[ -f "${CADENCE_DIR}/.env" ]]; then
  PUSHOVER_USER="$(sed -n 's/^PUSHOVER_USER=//p' "${CADENCE_DIR}/.env" | tail -n1)"
  PUSHOVER_TOKEN="$(sed -n 's/^PUSHOVER_TOKEN=//p' "${CADENCE_DIR}/.env" | tail -n1)"
  # Tolerate optionally quoted values.
  PUSHOVER_USER="${PUSHOVER_USER%\"}"; PUSHOVER_USER="${PUSHOVER_USER#\"}"
  PUSHOVER_TOKEN="${PUSHOVER_TOKEN%\"}"; PUSHOVER_TOKEN="${PUSHOVER_TOKEN#\"}"
fi

notify_failure() {
  local message="$1"
  [[ -n "$PUSHOVER_USER" && -n "$PUSHOVER_TOKEN" ]] || return 0
  command -v curl >/dev/null 2>&1 || return 0
  curl -fsS --max-time 20 \
    --data-urlencode "token=${PUSHOVER_TOKEN}" \
    --data-urlencode "user=${PUSHOVER_USER}" \
    --data-urlencode "title=Cadence backup FAILED" \
    --data-urlencode "message=${message}" \
    --data-urlencode "priority=1" \
    https://api.pushover.net/1/messages.json >/dev/null 2>&1 || true
}

# Any unexpected failure (set -e) alerts before the script exits. The retry loop
# below swallows its own expected attempt failures via `if`, so this fires only on
# a genuinely fatal step (dump, local validation, or exhausted uploads via the
# explicit exit path).
err_trap() {
  local exit_code=$?
  notify_failure "Backup ${BACKUP_NAME} failed (exit ${exit_code}, line ${BASH_LINENO[0]:-?}) on $(hostname). See backup-cadence.log."
}
trap err_trap ERR

# Upload the staged dir under its .partial name and verify every file landed,
# retrying the whole copy+verify to ride out pCloud's eventually-consistent
# listing. Returns non-zero only after all attempts fail.
upload_and_verify() {
  local attempt
  for ((attempt = 1; attempt <= UPLOAD_ATTEMPTS; attempt++)); do
    /usr/bin/rclone purge "$REMOTE_PARTIAL" 2>/dev/null || true
    if ! /usr/bin/rclone copy "$backup_dir" "$REMOTE_PARTIAL"; then
      echo "Upload attempt ${attempt}/${UPLOAD_ATTEMPTS}: copy failed, retrying in ${VERIFY_SETTLE_SECONDS}s"
      sleep "$VERIFY_SETTLE_SECONDS"
      continue
    fi
    # Let pCloud's listing catch up with the just-written files (the large cadence
    # dump can lag the copy) before checking.
    sleep "$VERIFY_SETTLE_SECONDS"
    if /usr/bin/rclone check "$backup_dir" "$REMOTE_PARTIAL" --one-way; then
      return 0
    fi
    echo "Upload attempt ${attempt}/${UPLOAD_ATTEMPTS}: verification failed, retrying"
    sleep "$VERIFY_SETTLE_SECONDS"
  done
  return 1
}

mkdir -p "$backup_dir"
cd "$CADENCE_DIR"

echo "[$(date --iso-8601=seconds)] Creating ${BACKUP_NAME}"

# Sweep leftover partial upload dirs from previously failed runs. They are
# dot-prefixed, so the published-backup retention sweep below (which only matches
# `cadence-*`) never trims them and they would otherwise accumulate invisibly.
mapfile -t stale_partials < <(
  /usr/bin/rclone lsf "$REMOTE_ROOT" --dirs-only 2>/dev/null \
    | sed 's:/$::' \
    | grep -E '^\.cadence-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}\.partial$' \
    || true
)
for partial in "${stale_partials[@]:-}"; do
  [[ -n "$partial" ]] || continue
  echo "Removing stale partial ${partial}"
  /usr/bin/rclone purge "${REMOTE_ROOT}/${partial}" 2>/dev/null || true
done

# Transactionally consistent dumps of both databases on the shared instance, in
# pg_restore's custom format. The `cadence` role owns/accesses both (the backend
# and the litellm proxy both connect as cadence:cadence).
/usr/bin/docker compose exec -T db \
  pg_dump -U cadence -d cadence -Fc \
  >"${backup_dir}/database-cadence.dump"

/usr/bin/docker compose exec -T db \
  pg_dump -U cadence -d litellm -Fc \
  >"${backup_dir}/database-litellm.dump"

# Deployment configuration for disaster recovery: the compose file and the root
# .env (secrets included — they live only in this pCloud space, same policy as the
# paperless backup). .env is included only if present.
config_files=(docker-compose.yml)
[[ -f .env ]] && config_files+=(.env)
tar -czf "${backup_dir}/configuration.tar.gz" "${config_files[@]}"

/usr/bin/docker compose images >"${backup_dir}/docker-images.txt"
(
  cd "$backup_dir"
  /usr/bin/sha256sum \
    database-cadence.dump \
    database-litellm.dump \
    configuration.tar.gz \
    docker-images.txt \
    >SHA256SUMS
)

# Validate every artifact before sending anything off-host.
/usr/bin/docker compose exec -T db \
  pg_restore --list <"${backup_dir}/database-cadence.dump" >/dev/null
/usr/bin/docker compose exec -T db \
  pg_restore --list <"${backup_dir}/database-litellm.dump" >/dev/null
tar -tzf "${backup_dir}/configuration.tar.gz" >/dev/null

# Upload under a temporary name, verify (with retries), then publish atomically.
if ! upload_and_verify; then
  /usr/bin/rclone purge "$REMOTE_PARTIAL" 2>/dev/null || true
  echo "All ${UPLOAD_ATTEMPTS} upload attempts failed for ${BACKUP_NAME}"
  notify_failure "Backup ${BACKUP_NAME} failed: ${UPLOAD_ATTEMPTS} upload/verify attempts to pCloud all failed on $(hostname). See backup-cadence.log."
  exit 1
fi
/usr/bin/rclone moveto "$REMOTE_PARTIAL" "${REMOTE_ROOT}/${BACKUP_NAME}"

# Retain only the newest KEEP_BACKUPS completed backup directories.
mapfile -t remote_backups < <(
  /usr/bin/rclone lsf "$REMOTE_ROOT" --dirs-only \
    | sed 's:/$::' \
    | grep -E '^cadence-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}$' \
    | sort -r
)

for ((index = KEEP_BACKUPS; index < ${#remote_backups[@]}; index++)); do
  echo "Removing expired backup ${remote_backups[$index]}"
  /usr/bin/rclone purge "${REMOTE_ROOT}/${remote_backups[$index]}"
done

echo "[$(date --iso-8601=seconds)] Backup completed: ${REMOTE_ROOT}/${BACKUP_NAME}"
