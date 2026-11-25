#!/usr/bin/env bash
# ~/bin/deploy-qa.sh — deploy Cadence QA from a fixed git ref.
set -euo pipefail

APP_DIR="$HOME/apps/cadence"     # QA checkout (DEV: ~/apps/cadence-dev, PRD: ~/apps/cadence-prd)
REF="release/2026.12"            # QA: release branch | DEV: main | PRD: a tag, e.g. v2026.11.0

cd "$APP_DIR"

# Refuse to deploy over local edits (untracked files like logs are fine).
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Local changes in $APP_DIR — commit/stash them first." >&2
  exit 1
fi

before=$(git rev-parse --short HEAD)
git fetch --tags --prune origin

if git show-ref --verify --quiet "refs/remotes/origin/$REF"; then
  # A branch: switch to it and fast-forward only (never merge or rewrite).
  git switch "$REF" 2>/dev/null || git switch -c "$REF" --track "origin/$REF"
  git merge --ff-only "origin/$REF"
elif git show-ref --verify --quiet "refs/tags/$REF"; then
  # A tag (PRD): check out exactly that commit.
  git switch --detach "$REF"
else
  echo "Unknown branch or tag: $REF" >&2
  exit 1
fi

after=$(git rev-parse --short HEAD)
echo "Deploying $REF: $before -> $after"
git log --oneline "$before..$after" || true

# Build, start, and wait until every service with a healthcheck is healthy
# (the backend runs its database migrations on start).
docker compose up -d --build --wait

docker image prune -f >/dev/null   # drop dangling old images (keeps the SD card from filling)
echo "Deployed $REF at $after."
echo "Rollback: git -C $APP_DIR switch --detach $before && pose up -d --build --wait)"
