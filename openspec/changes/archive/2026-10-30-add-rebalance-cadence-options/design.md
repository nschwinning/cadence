## Context

Today every AI-built paper-trading session is rebalanced once per trading day. Cadence is not a user choice: `ai_portfolio/flows/build.py` hardcodes `schedule_mode = ScheduleMode.DAILY_REBALANCING` on the shell session, and the two cron fan-out endpoints in `api/routers/ai_portfolio.py` both target `schedule_mode == DAILY_REBALANCING.value` — `rebalance_daily` rebalances the whole portfolio on weekday runs, `rebalance_crypto_daily` rebalances only the crypto sleeve on weekend runs. The weekday/weekend split lives entirely in the cron *schedule* (docker-compose), not in code.

Relevant facts established by reading the code this session:

- `ScheduleMode` (`paper_trading/constants.py`) is a `StrEnum` persisted via a **non-native string enum column** (`_enum_column`, `server_default=SCHEDULED`). Adding enum members needs no *check-constraint* change — but the column was created as `VARCHAR(17)`, sized to the then-longest value `DAILY_REBALANCING` (17 chars). The new values `WEEKLY_REBALANCING` (18) and `MONTHLY_REBALANCING` (19) do not fit, so **a one-line widening migration is required** (`ALTER COLUMN ... TYPE VARCHAR(32)`). This corrects the initial assumption that the change was migration-free.
- `AIBuildParams` (`ai_portfolio/params.py`) is the frozen build payload (`to_payload`/`from_payload`); it carries no cadence field today.
- There is **no `last_rebalanced_at` anchor** on the session. `last_run_at` exists but is not rebalance-specific.
- Opening allocation is already deferred to the first scheduled rebalance (`route-initial-allocation-through-rebalance` / `defer-initial-allocation-to-daily-rebalance`): a freshly built session sits in cash until its first scheduled run, and `build_orders_settled` (`ai_portfolio/events.py`) treats a never-allocated session as ready.

## Goals / Non-Goals

**Goals**
- Let a build choose a rebalance cadence of daily, weekly, or monthly, frozen at build.
- Fan the daily cron out to all three cadences while rebalancing each session at most once per its period, with calendar boundaries that self-heal across weekends, holidays, and missed runs.
- Guarantee a mixed stock+crypto weekly/monthly session rebalances its whole portfolio exactly once per period, never splitting its crypto sleeve onto a weekend run.
- Ship with only a **single column-widening migration** (`schedule_mode` → `VARCHAR(32)`) and no change to cron times, the agent/prompt, sizing, guardrails, cash-buffer, redeploy, or readiness-gate logic.

**Non-Goals**
- Free-form "every N days" cadence (discrete enum only).
- Editing cadence on a live session (frozen at build, like every other option).
- Changing the cron schedule/times or docker-compose.
- A separate weekend behavior for weekly/monthly sessions.
- Touching the `MANUAL` / `SCHEDULED` scheduling modes or their semantics.

## Decisions

### D1 — Discrete enum, not free-form interval
Add `WEEKLY_REBALANCING` and `MONTHLY_REBALANCING` to `ScheduleMode` (values `"WEEKLY_REBALANCING"` / `"MONTHLY_REBALANCING"`). The user-facing cadence is `daily | weekly | monthly`. Discrete buckets keep the Build UI a simple selector and make the existing session-comparison chart's cadence dimension clean to read. The enum is non-native, but the longer values exceed the column's `VARCHAR(17)`, so the storage column is widened to `VARCHAR(32)` (see Migration Plan).

### D2 — Frozen at build
A new `rebalance_cadence` field on `AIBuildParams` (default daily) threads through `to_payload`/`from_payload`; `build.py` maps it to the session's `schedule_mode` instead of hardcoding daily. This matches every other per-session option (model, guardrails, `use_fundamentals`, `use_technical_indicators`, benchmark) — all frozen at build, none editable on a live session. Daily default means an unspecified build behaves exactly as today.

### D3 — Calendar-boundary due-check (not fixed-date)
The daily cron now targets daily + weekly + monthly sessions and applies a pure, unit-testable due-check before starting each one:

```
def rebalance_due(schedule_mode, last_rebalanced_at, now, tz) -> bool:
    if schedule_mode == DAILY_REBALANCING:          return True
    if last_rebalanced_at is None:                  return True   # never allocated ⇒ due now
    last  = last_rebalanced_at.astimezone(tz).date()
    today = now.astimezone(tz).date()
    if schedule_mode == WEEKLY_REBALANCING:         return today.isocalendar()[:2] != last.isocalendar()[:2]
    if schedule_mode == MONTHLY_REBALANCING:        return (today.year, today.month) != (last.year, last.month)
```

Boundaries are evaluated in the **US market timezone (Eastern)**: a weekly session is due on the first cron run of a new ISO (year, week); a monthly session on the first run of a new (year, month). This is deliberately a *calendar-boundary* rule, not a fixed-date "rebalance on the 1st / on Monday" rule: a fixed date silently skips the whole period whenever that date lands on a weekend or market holiday. With the boundary rule, if the 1st is a Saturday the first weekday cron run that month (say Monday the 3rd) crosses the month boundary and fires — nothing is skipped, no fixed-date trap.

### D4 — Single shared cadence; weekend crypto cron stays daily-only (the double-rebalance fix)
`rebalance_crypto_daily` keeps its existing `schedule_mode == DAILY_REBALANCING` filter unchanged, so weekly/monthly sessions are automatically excluded from the weekend crypto run. A weekly/monthly session is therefore rebalanced as a whole, exactly once per period, on a weekday cron run. This is the deliberate fix for the double-rebalance case: a mixed stock+crypto monthly session must not rebalance its crypto on Saturday the 1st and its stocks on Monday the 3rd. The honest consequence — a weekly/monthly session's crypto is not tended on weekends between rebalances — is correct semantics for "rebalanced weekly/monthly" and is documented in the spec.

### D5 — Anchor derived from the latest succeeded rebalance event (migration-free)
The due-check's `last_rebalanced_at` is derived from the timestamp of the session's **latest successfully-completed rebalance AI-portfolio event**, not from a new column.

- **Chosen: derive from event history.** No migration; self-correcting and idempotent. A run that fails or is skipped for market-closed does *not* produce a succeeded rebalance event, so the anchor does not advance and the session stays due and is retried on the next trigger — the same self-healing property the deferred-initial-allocation flow already relies on. A succeeded "hold, no orders" rebalance *does* advance the anchor (the period's rebalance genuinely happened — the AI chose to hold). Cost is one bounded query per non-daily session per trigger (daily sessions skip the lookup entirely); the candidate set is already capped, and the query is batchable if needed.
- **Rejected: new nullable `last_rebalanced_at` column.** O(1) compare, but needs a migration plus a stamping write on each successful rebalance, and a stale/half-written stamp would be a new correctness surface. Not worth it when the event history already answers the question.
- **Rejected: `session_metadata` JSONB marker.** Migration-free too, but still a write-each-run marker with the same staleness risk as a column, and less legible than the authoritative event log.

### D6 — Never-allocated ⇒ due now (preserves the opening-allocation invariant)
Because a never-rebalanced session has no succeeded rebalance event, the anchor is `None` and the session is due now regardless of cadence. The opening allocation therefore still flows through the standard rebalance path on the next due weekday run, preserving the `route-initial-allocation-through-rebalance` invariant. Cadence only governs *when subsequent* rebalances fire.

### D7 — Distinct skip reason
A session skipped solely because it is not yet due is reported under a new `skipped_not_due` bucket on `AIDailyRebalanceResponse`, kept separate from `skipped_already_running` and `skipped_awaiting_build_fill`, so operators can see cadence gating in the cron output. Check order in `rebalance_daily`: already-running → awaiting-build-fill (deferred) → not-due → start. A never-allocated session is ready (not deferred) and due, so it starts.

### D8 — Surfacing
`PaperTradingSessionRead` gains a `rebalance_cadence` field derived from `schedule_mode` (`DAILY_REBALANCING → "daily"`, etc.; any legacy/other mode → `"daily"`), mapped in the thin router layer. The build request schema gains an optional `rebalance_cadence` defaulting to daily. Frontend adds a cadence control to `BuildAIPortfolioCard`, the request type in `api/aiPortfolio.ts`, the read type in `types/api.ts`, and a session-detail fact tile mirroring the existing model/guardrails/fundamentals tiles.

### D9 — Build form: required radio, no pre-selected default
The Build card presents the cadence as a **radio group of exactly daily/weekly/monthly with no option pre-checked**; the user MUST select exactly one, and submission is blocked until they do. This is a deliberate split from the API/compatibility default: the request schema still defaults an *absent* cadence to daily and the read model still resolves legacy sessions to daily (D8), but the UI never silently picks daily on the user's behalf — cadence is a real strategy decision the operator should make consciously at build time, like asset scope. The form always sends an explicit cadence, so the API default only ever applies to non-form callers and pre-existing sessions.

## Risks / Trade-offs

- **Per-trigger event query for non-daily sessions.** Mitigated: daily sessions (the overwhelming majority, and the default) skip the lookup; non-daily sessions are a small subset under the existing cap; the query is bounded and batchable.
- **Timezone correctness.** The due-check buckets strictly by Eastern calendar date, so DST transitions shift only the wall-clock instant of the boundary, not which date a run falls on. Unit tests cover week/month boundary crossings in ET.
- **First trading day of a period is a holiday.** The rebalance skips (market-closed), the anchor does not advance, and the session is retried the next trading day — still inside the same period bucket. Correct.
- **Weekly/monthly crypto not tended on weekends.** Intended semantics for a non-daily cadence; documented in the `ai-paper-trading` opening-allocation requirement and the `daily-rebalancing` weekend-crypto requirement.

## Migration Plan

One migration: widen `paper_trading_sessions.schedule_mode` from `VARCHAR(17)` to `VARCHAR(32)` so the longer `WEEKLY_REBALANCING` / `MONTHLY_REBALANCING` values fit (migration `e2a4c6b8d0f1`, `down_revision c4e6a8b0d2f4`). It rewrites no rows and leaves existing `DAILY_REBALANCING` / `SCHEDULED` / `MANUAL` values untouched; the downgrade narrows back to `VARCHAR(17)` (safe only while no weekly/monthly rows exist). The due-check anchor still needs no column — it is derived from existing rebalance-event history. Because `Base.metadata.create_all` sizes the column from the current enum, a freshly provisioned database gets the wider column automatically; only already-provisioned databases (prod and any persistent test DB) need the migration applied. Deploy backend and frontend together, running the migration first. The build request's cadence is optional and defaults to daily, so existing sessions are unaffected. Rollback is a plain revert plus the downgrade; any session built weekly/monthly during the window falls back to daily by the read mapping.

## Open Questions

None.
