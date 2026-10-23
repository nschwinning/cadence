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
# backup. Only the newest KEEP_BACKUPS backups are retained.
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
readonly KEEP_BACKUPS=14
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

mkdir -p "$backup_dir"
cd "$CADENCE_DIR"

echo "[$(date --iso-8601=seconds)] Creating ${BACKUP_NAME}"

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

# Upload under a temporary name, verify, then publish it atomically.
/usr/bin/rclone purge "$REMOTE_PARTIAL" 2>/dev/null || true
/usr/bin/rclone copy "$backup_dir" "$REMOTE_PARTIAL"
/usr/bin/rclone check "$backup_dir" "$REMOTE_PARTIAL" --one-way
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
