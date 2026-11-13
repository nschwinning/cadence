## Context

`reconcile_orders(db, broker, owner_kind=BOT)` runs at the top of `run_bot_tick`, after the
`is_market_open()` early return. The engine polls a submitted order only briefly; a still-working
order is left `submitted` with a 2-minute lease for reconciliation. Ticks after 16:00 ET return
before reconciling, so a fill from the final minutes waits until the next session. The daily bot
snapshot job (`POST /bots/snapshot-daily` → `run_bot_snapshots`, 16:15 ET weekdays) marks
positions at the broker and records one snapshot per active bot.

## Goals / Non-Goals

**Goals:** book late bot fills the same evening, before that day's snapshot; surface the count.

**Non-Goals:** reconciling AI-portfolio or admin records in this job (AI sessions trade at the
09:35 rebalance and reconcile before every run; "Reconcile now" covers everything); running
reconciliation inside closed-market ticks; correcting past snapshots.

## Decisions

1. **Where:** at the start of `run_bot_snapshots`, before the active-session loop (so the
   loaded sessions see the booked positions/cash). Bot-owned records only, mirroring the tick.
   `run_bot_snapshots` returns a small result (`snapshots`, `reconciled`) instead of a bare count;
   the router maps it to `BotSnapshotResponse(snapshots, reconciled, orchestrator_snapshots)`.
2. **Failure isolation:** `reconcile_orders` already isolates each record (commit/rollback per
   row) and treats broker lookup errors as "remaining". The call is additionally wrapped so an
   unexpected exception rolls back, is logged, counts 0, and the snapshots proceed.
3. **Order safety:** reconciliation only touches records whose lease expired, uses
   `FOR UPDATE SKIP LOCKED`, and books exactly once — safe to run concurrently with a straggling
   tick or the AI snapshot job.
4. **Expired day orders:** a DAY order that never filled is reported cancelled/expired after the
   close, so it is closed out without booking — also a same-evening cleanup.

## Risks / Trade-offs

- A record whose broker lookup fails stays unbooked until the next pass (tick or manual) —
  unchanged behaviour.

## Migration Plan

None. Deploy only; existing unbooked records are picked up at the next 16:15 run.

## Open Questions

None.
