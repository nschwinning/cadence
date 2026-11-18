#!/bin/bash
# One-shot setup run by the `keycloak-init` service after Keycloak is healthy.
#
# Optional one-time seed of a Cadence admin: when CADENCE_ADMIN_USERNAME and
# CADENCE_ADMIN_PASSWORD are set and the realm has not been seeded before, create
# that user with the `admin` role and a TEMPORARY password (Keycloak makes the user
# choose a new one at first login), then mark the realm as seeded. The marker
# (realm attribute `cadenceAdminSeeded`) makes this a one-time action: a later
# restart never creates, overwrites or recreates the user, even if it was deleted.
set -euo pipefail

KCADM=/opt/keycloak/bin/kcadm.sh
SERVER="http://keycloak:8080/auth"

if [ -z "${KC_BOOTSTRAP_ADMIN_USERNAME:-}" ] || [ -z "${KC_BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
  echo "keycloak-init: no Keycloak admin credentials configured; nothing to do."
  exit 0
fi

for attempt in $(seq 1 30); do
  if "$KCADM" config credentials --server "$SERVER" --realm master \
      --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "keycloak-init: could not log in to Keycloak." >&2
    exit 1
  fi
  sleep 5
done

if [ -z "${CADENCE_ADMIN_USERNAME:-}" ] || [ -z "${CADENCE_ADMIN_PASSWORD:-}" ]; then
  echo "keycloak-init: CADENCE_ADMIN_USERNAME/PASSWORD not set; no admin seeded."
  exit 0
fi

if "$KCADM" get realms/cadence --fields attributes 2>/dev/null | grep -q '"cadenceAdminSeeded"'; then
  echo "keycloak-init: admin already seeded once; leaving users untouched."
  exit 0
fi

if "$KCADM" get users -r cadence -q "username=${CADENCE_ADMIN_USERNAME}" -q exact=true 2>/dev/null \
    | grep -q '"username"'; then
  echo "keycloak-init: user ${CADENCE_ADMIN_USERNAME} already exists; not changing it."
else
  "$KCADM" create users -r cadence -s "username=${CADENCE_ADMIN_USERNAME}" -s enabled=true >/dev/null
  "$KCADM" set-password -r cadence --username "$CADENCE_ADMIN_USERNAME" \
    --new-password "$CADENCE_ADMIN_PASSWORD" --temporary
  "$KCADM" add-roles -r cadence --uusername "$CADENCE_ADMIN_USERNAME" --rolename admin
  echo "keycloak-init: seeded admin ${CADENCE_ADMIN_USERNAME} (must change the password at first login)."
fi

"$KCADM" update realms/cadence -s 'attributes.cadenceAdminSeeded=true'
echo "keycloak-init: done."
