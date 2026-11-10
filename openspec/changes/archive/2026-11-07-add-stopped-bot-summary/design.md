## Context

See proposal.md — Why. The strategy-bots subsystem (`backend/src/cadence/strategy_bots/`)
follows the project package shape (models / service / constants / errors). A bot stops via
two paths — `service.stop_bot_session` (manual) and the kill-switch block in
`service._tick_session` — both of which today only set `status = STOPPED` with no reason or
timestamp. `bot_session_kpis` already computes current value, total return, realised/
unrealised P&L, available cash, best/worst closed round-trip (`bot_trade_extremes`), max
drawdown (`_max_drawdown` over the snapshot series, service.py ~863), and the benchmark
comparison (`_bot_benchmark_returns`). `bot.peak_value` is the persisted high-water mark.

The app already has a cached-AI pattern to mirror exactly: the universe evaluation
(`assets/universe_agent.py` + `assets/service.py`) builds a **tool-less** `build_agent`
with a Pydantic `output_type`, runs it once under `RECOMMENDER_AGENT_TIMEOUT_SECONDS`,
persists the result on a row alongside a **sha256 fingerprint of the inputs**
(`_universe_fingerprint`), and treats a timeout/SDK failure as a typed "unavailable"
error. `evaluation_outdated` compares the stored fingerprint to recompute.

## Goals / Non-Goals

**Goals:**
- Record `stop_reason` + `stopped_at` on every stop, from both stop paths.
- Serve a stopped-only **session summary** (stats + stop metadata + cached AI narrative).
- Extend best/worst round-trip data to carry exact entry/exit (price + time) and quantity.
- Generate the AI narrative lazily on first view and cache it behind an input fingerprint.

**Non-Goals:**
- No change to valuation, the tick loop, or the kill-switch threshold math.
- No backfill of `stop_reason`/`stopped_at` for pre-existing stopped rows.
- No AI summary for AI-portfolio (paper-trading) sessions.
- No eager/scheduled generation — lazy-on-view only.

## Decisions

### 1. Persist stop metadata + cached summary on `bot_sessions` (not a new table)
Add columns to `BotSession`: `stop_reason: str | None` (free-text holding
`'drawdown_kill_switch'` | `'manual'`, validated by a `StopReason` enum in `constants.py`,
matching the free-text `strategy_key`/`status` convention), `stopped_at: datetime | None`,
and for the cached narrative `summary_narrative: str | None`, `summary_fingerprint:
str | None`, `summary_model: str | None`, `summary_generated_at: datetime | None`.
One-to-one with the session, lazily filled → columns, not a side table (the universe
evaluation is a singleton row because it is global; a bot summary is per-session, so it
lives on the session row). **Alembic migration required** — the first strategy-bots
migration (prior changes rode on free-text `strategy_key`). All columns nullable so the
migration is a pure add with no backfill.

### 2. Set stop metadata at both stop sites
`stop_bot_session` sets `stop_reason = StopReason.MANUAL`, `stopped_at = now(UTC)`. The
kill-switch block in `_tick_session` sets `stop_reason = StopReason.DRAWDOWN_KILL_SWITCH`
and `stopped_at = tick_now` (reuse the tick's clock for determinism). No threshold logic
changes.

### 3. Extend `TradeExtreme` + `bot_trade_extremes` in place
`TradeExtreme` gains `quantity`, `entry_price`, `entry_at`, `exit_price`, `exit_at`. The
helper already reconstructs round-trips; it currently discards the entry quantity
(`_entry_qty`) and does not carry the entry trade's `created_at`. Change `open_basis` to
store `(entry_price, entry_qty, entry_fees, entry_at)` and populate the new fields from the
paired buy/sell (`exit_price = trade.filled_price`, `exit_at = trade.created_at`,
`quantity = trade.quantity`). `BotKpis`/`BotKpisRead` + the TS `TradeExtreme` type and the
existing best/worst tiles pick up the richer shape; existing KPI consumers are additive-safe.

### 4. Separate summary assembly from AI generation; new `GET /bots/sessions/{id}/summary`
A new `bot_session_summary(session, bot, agent)` service function:
1. Guards: if `bot.status != STOPPED`, raise a typed error the router maps to 409 (keeps
   the active-bot "no summary" contract explicit and avoids any AI call).
2. Assembles the stats block by **reusing** `bot_session_kpis` (final value, total return,
   best/worst, benchmark excess), `bot.peak_value`, the max-drawdown helper, and lifespan =
   days from the session start (first tick / created_at) to `stopped_at`; computes closed-
   trade count and win rate from the same round-trip walk used by `bot_trade_extremes`
   (extend it to return the full list, or add a sibling helper — decided in tasks).
3. Computes a sha256 **summary fingerprint** over the stats + stop metadata (the
   user-visible inputs the narrative is derived from — deliberately excluding live current
   value drift so a stopped bot's fingerprint is stable).
4. If `summary_fingerprint` matches the stored one, returns the cached narrative; else
   calls the agent, persists `summary_narrative`/`summary_fingerprint`/`summary_model`/
   `summary_generated_at`, and returns it. Agent failure (timeout/SDK) is caught → narrative
   returned as `None`, nothing persisted, so a later view retries.

A dedicated endpoint (not folded into `/kpis`) keeps KPIs free of an AI side effect and
lets the frontend fetch/poll the summary independently with its own loading state.

### 5. New AI agent module mirroring `universe_agent.py`
`strategy_bots/summary_agent.py`: a tool-less `build_agent` with a Pydantic
`BotSummaryOutput` (narrative markdown, maybe a one-line headline), a
`BotSessionSummaryAgent` Protocol seam (real impl + injectable fake via a `get_*`
dependency) so tests run with no network, run once under the shared agent timeout, same
typed-unavailable failure handling. Model id persisted on the row (`get_*_model()`),
like the universe evaluation.

## Risks / Trade-offs

- **AI latency on first view** → the endpoint is separate and the frontend shows a loading
  state; stats render immediately from cache-independent computation even if the narrative
  is still generating or failed.
- **Fingerprint over live-ish inputs could thrash** → fingerprint only stop-stable inputs
  (final/realized figures + stop metadata), not the live current value, so a stopped bot's
  narrative is generated once and stays cached.
- **Round-trip reconstruction correctness** → unchanged pairing logic; relies on the
  existing one-position-per-symbol + full-exit invariants already documented on the helper.
- **Enum vs free-text for `stop_reason`** → free-text column + Python enum (mirrors
  `status`/`strategy_key`) avoids a PG enum migration and keeps forward-compatibility.

## Migration Plan

1. Add the six nullable columns to `BotSession`; generate one Alembic migration
   (`uv run alembic revision --autogenerate`), review, and apply. Downgrade drops them.
2. No data backfill: pre-existing stopped rows keep `stop_reason`/`stopped_at` = NULL; the
   summary renders those as "unknown"/absent and still produces stats + narrative.
3. Rollback = downgrade the migration; the feature is additive and off for active bots.

## Open Questions

None blocking — the enum values, column placement, and endpoint shape are decided above.
