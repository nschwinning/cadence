---
name: db-migration
description: Create and review Alembic migrations safely for the Cadence PostgreSQL database — autogenerate, review the diff, verify upgrade/downgrade round-trip, and flag destructive or locking operations. Use when models change or a schema/data migration is needed.
allowed-tools: Bash(alembic:*)
metadata:
  author: cadence
  version: "1.0"
---

Create and review an Alembic migration safely.

## Before generating
1. Locate the Alembic setup (`alembic.ini`, `migrations/` or `alembic/` dir, `env.py`) — discover it, don't assume.
2. Ensure the SQLAlchemy models reflect the intended final schema. The migration derives from the models.
3. Confirm the DB is at `head` (`alembic current`) so autogenerate produces a clean diff.

## Generate
- Autogenerate: `alembic revision --autogenerate -m "<concise description>"`.
- **Always review the generated script by hand.** Autogenerate misses: renames (it drops+adds, losing data), server defaults, check constraints, enum changes, and index intent. Fix these explicitly.

## Review checklist
- [ ] `downgrade()` is correct and truly reverses `upgrade()` — never leave it as `pass`.
- [ ] No unintended `drop_table`/`drop_column` from a model the ORM simply can't see.
- [ ] Column renames use `op.alter_column`, not drop+add (which loses data).
- [ ] New foreign keys and frequent filter columns get indexes.
- [ ] Destructive or long-locking ops on large tables are flagged; split schema change from data backfill when risky.
- [ ] NOT NULL added to an existing table has a safe default or a backfill step first.

## Verify
- Round-trip on a scratch/test DB: `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` again. Report the actual output.

## After
- Summarize what the migration does, confirm the round-trip result, and list any locking/backfill risks for production.
