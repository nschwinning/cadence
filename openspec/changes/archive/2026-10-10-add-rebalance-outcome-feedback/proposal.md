## Why

Cadence already assembles a rich per-session/per-day learning record in
`session_daily_run_snapshots.document` (realized P&L per day, orders with filled
prices, account valuation, fees, gate/skip counts), written by the
daily-run-snapshot cron. But that record is **write-only** — nothing ever reads it
back into a decision. The AI rebalance prompt, built by `_build_rebalance_input` in
`backend/src/cadence/ai_portfolio/agent.py`, carries **zero** prior-outcome
context, so every day's rebalance is blind to how the agent's own previous
decisions actually performed — including whether its churn is being eaten by
transaction costs. Closing this loop lets the agent see a short, recent,
cost-forward history of its results and adjust — turning a collected-but-unused
dataset into an active input.

## What Changes

- **A new per-session opt-in flag `learning_feedback_enabled` (default OFF),
  frozen at build time** — matching the existing `use_technical_indicators`,
  `stop_loss_enabled`, and `risk_guardrails_enabled` knobs. It is chosen once on
  the build card and **not** live-toggleable, so two sessions stay comparable and a
  session's strategy identity is stable. Existing sessions are backfilled to OFF (no
  retroactive behavior change).
- **A new per-session `learning_feedback_window` (number of recent days), also
  chosen on the build card and frozen at build time** — mirroring the stop-loss
  threshold / guardrail parameters. It is meaningful only when the flag is on,
  pre-filled from a configured default, and stored per session so each portfolio's
  learning depth is part of its fixed, comparable identity rather than a global
  env knob.
- A new read helper fetches the most recent N daily-run snapshots for a session
  (N = the session's frozen window, most-recent-first), reusing the existing
  snapshot table — no new snapshot table.
- **The transaction fee assessed on each executed trade is now persisted on the
  trade** (a new `fee` column on `paper_trades`, set at the single `record_trade`
  choke point that already computes it) so the daily-run learning document can
  carry each order's fee and the day's total fees. This makes the cost-forward
  distillation's "fees paid" and net-of-fees realized P&L exact rather than
  approximate. Historical trades recorded before this column default to a zero
  fee and are not backfilled.
- When the flag is on, the rebalance flow threads those snapshots into
  `_build_rebalance_input`, which renders a new **advisory** "Recent run outcomes"
  section. The distillation is **cost/churn-forward**: each per-day line leads with
  net-of-fees realized P&L, then fees paid and order/churn count, then end-of-day
  valuation/return and notable gate/skip counts. It is a pure, deterministic,
  unit-testable helper.
- A new setting `LEARNING_FEEDBACK_DEFAULT_WINDOW` (default `5`) supplies only the
  **build-form default / fallback** for the per-session window (like
  `STOP_LOSS_DEFAULT_PCT` and the `GUARDRAIL_DEFAULT_*` settings); it is not read at
  rebalance time. There is no global env window and no global kill switch — a
  session participates purely by its frozen flag, and its depth is its frozen
  window. When a session has the flag off or has no snapshots yet, the prompt is
  byte-identical to today's.
- The learning block is **context only** — it adds no hard constraints and does
  not touch executor sizing, guardrails, numeric clamps, or valuation. Only the
  rebalance flow consumes it; the build flow is unaffected.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ai-paper-trading`: a new per-session, build-time-frozen opt-in flag and learning
  window; when the flag is on, the AI rebalance decision incorporates that session's
  own recent prior daily-run outcomes (cost-forward), up to its frozen window, as
  advisory prompt context. The consolidated daily-run learning snapshot additionally
  records each filled order's assessed transaction fee and the day's total fees
  (persisted on the trade), so the cost-forward distillation is exact.
- `app-shell`: the AI build card exposes the new learning-feedback opt-in control
  and its window input, and the session read/detail surfaces whether learning
  feedback is enabled and, when enabled, its window.

## Impact

- **Backend:**
  - `paper_trading/models.py` — new `learning_feedback_enabled: bool` column on
    `PaperTradingSession` (non-nullable, server default false) and a nullable
    `learning_feedback_window: int | None` column (meaningful only when enabled),
    both frozen at build — mirroring `stop_loss_enabled` / `stop_loss_pct`.
  - Alembic migration — add the two session columns (`learning_feedback_enabled`
    with a `false` server default, backfilled to false; `learning_feedback_window`
    nullable) and the `paper_trades.fee` column (non-nullable, `0` server default,
    backfilled to 0) so existing rows are unaffected; `down_revision` = current head.
  - `ai_portfolio/params.py` — `AIBuildParams` gains `learning_feedback_enabled`
    (default false) and `learning_feedback_window` (default None) threaded through
    its `to_dict`/`from_payload` round-trip, like the other opt-in knobs.
  - `ai_portfolio/flows/build.py` — persists the flag and window on the new session
    at build (defaulting the window to `LEARNING_FEEDBACK_DEFAULT_WINDOW` when the
    flag is on and no window was supplied).
  - `paper_trading/service.py` — new read-only `list_daily_run_snapshots(session,
    session_id, limit)` helper (mirrors the existing single-row
    `get_daily_run_snapshot`; orders by `run_date DESC`, limited to N);
    `record_trade` additionally stores the asset-class-aware fee it already
    computes onto the new `PaperTrade.fee` column.
  - `paper_trading/models.py` — new `fee: float` column on `PaperTrade`
    (non-nullable, server default `0`) holding the transaction cost assessed when
    the trade was recorded.
  - `ai_portfolio/snapshots.py` — `_order_document` includes each order's `fee`
    and `_build_run_document` records the day's `fees_total` (sum of the day's
    order fees) in the learning document.
  - `ai_portfolio/agent.py` — `_build_rebalance_input` gains an optional
    prior-outcomes argument and renders the advisory "Recent run outcomes"
    section; a new pure, cost-forward distillation helper formats snapshot
    documents into compact per-day lines.
  - `ai_portfolio/flows/rebalance.py` — `run_rebalance_event` fetches the window
    only when the session's `learning_feedback_enabled` is true, using the
    session's frozen `learning_feedback_window`, and passes it to
    `_build_rebalance_input`.
  - `config.py` — new `LEARNING_FEEDBACK_DEFAULT_WINDOW: int = 5` setting (build
    default / fallback only).
  - `api/schemas.py` — the AI build request accepts `learning_feedback_enabled`
    (default false) and an optional `learning_feedback_window` (validated positive
    when the flag is on; defaults to the configured default); the session read
    exposes both.
- **Frontend:**
  - `BuildAIPortfolioCard.tsx` — new opt-in control for learning feedback plus a
    window (days) input pre-filled from the default and hidden/disabled while the
    toggle is off, alongside the existing technical-indicators / stop-loss /
    guardrails controls.
  - session read TS type + session detail — surface whether learning feedback is
    enabled and, when enabled, its window (a fact tile, matching the "Risk
    guardrails" surface).
- **No** change to the daily-run snapshot's assembly *sequencing* or cron, no
  `run_stats` sourcing for the learning window, no new API endpoint, and no change
  to executor sizing, guardrails, or valuation. The only write-path change is
  recording the per-trade fee (already computed at `record_trade`) and surfacing it
  in the learning document.
- **Compatibility:** default-OFF per session; existing sessions backfilled to OFF
  (identical behavior to today).
