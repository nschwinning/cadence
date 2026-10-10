# Design

## Context

See proposal.md - Why. The daily-run snapshot is already assembled and persisted
per session/day in `session_daily_run_snapshots.document` (a mostly-JSONB column)
by the `assemble_daily_run_snapshots` cron. `paper_trading/service.py` exposes a
single-row reader `get_daily_run_snapshot(session, session_id, run_date)` and the
recorder `record_daily_run_snapshot(...)`. The rebalance prompt is assembled by
`_build_rebalance_input(...)` in `ai_portfolio/agent.py` (pure/deterministic,
unit-tested). `run_rebalance_event` now lives in `ai_portfolio/flows/rebalance.py`
after the service split; it owns the DB session and the agent invocation, so it is
the natural place to decide whether to fetch the window and to pass it down.
Standard rebalances and the crypto-scoped variant both flow through
`_build_rebalance_input`.

Cadence already has three per-session opt-in knobs that are chosen on the build
card and **frozen at build time**: `use_technical_indicators`, `stop_loss_enabled`,
and `risk_guardrails_enabled` (columns on `PaperTradingSession`, threaded through
`AIBuildParams`, surfaced on the build request + session read + build card). Two of
them pair an enable flag with a frozen parameter sourced from a configured default:
`stop_loss_enabled`/`stop_loss_pct` (default `STOP_LOSS_DEFAULT_PCT`) and
`risk_guardrails_enabled`/`max_asset_class_pct`/`min_positions`/`max_invested_pct`
(defaults `GUARDRAIL_DEFAULT_*`). The parameter column is nullable and meaningful
only when its flag is on. The user chose to make learning feedback a fourth knob of
exactly this kind — an enable flag **plus a frozen learning window** — not a
global-only toggle and not live-switchable, because a session that flips learning on
and off (or silently changes its depth) mid-life is not comparable to other sessions
and loses a stable strategy identity. The learning window in particular is a
build-time choice (like the stop-loss threshold), not a global env knob.

## Goals / Non-Goals

**Goals**
- A per-session, build-time-frozen opt-in (`learning_feedback_enabled`, default
  OFF) plus a build-time-frozen learning window (`learning_feedback_window`)
  controlling whether and how deeply the session's rebalance agent sees its own
  recent outcomes, consistent with the existing enable-flag-plus-frozen-parameter
  knobs (stop-loss, guardrails).
- Surface a short, recent, **cost/churn-forward** distilled outcome history to the
  rebalance agent as advisory context, sourced only from daily-run snapshots.
- Keep the distillation pure and deterministic so it is unit-testable and produces
  a byte-identical prompt when the feature is off (per session or globally) or
  there is no history.
- Existing sessions default OFF (backfilled), so no retroactive behavior change.

**Non-Goals**
- No change to the daily-run snapshot's assembly *sequencing* or cron, and no
  recomputation of indicators or re-running of the agent (the one write-path change
  is recording the per-trade fee and surfacing it in the learning document — see
  D8).
- No change to the build flow's decisioning, executor sizing, guardrails, numeric
  clamps, or valuation (build only *persists* the new flag; it does not consume
  outcomes). The new per-trade fee is the fee `record_trade` *already* computes; the
  session's cumulative `total_fees` and net valuation are unchanged.
- No new snapshot table; no new API endpoint. (A `fee` column is added to
  `paper_trades`, and the two per-session flag/window columns to
  `paper_trading_sessions`.)
- No live/after-build toggling of the flag or window (no PUT endpoint); both are
  frozen like the other opt-in knobs and their parameters.
- No global/runtime learning window; the window is a per-session build-time value.
- No sourcing from `ai_portfolio_events.run_stats`.

## Decisions

### D1 — Source: daily-run snapshots, not `run_stats`
Use `session_daily_run_snapshots.document`. It is the purpose-built, consolidated
per-day record (realized P&L, orders + filled prices, **per-order and per-day fees
(see D8)**, valuation, gate/skip counts) and is already keyed `(session_id, run_date)`
with an index, so a "latest N for a session" read is cheap. *Alternative:*
`ai_portfolio_events.run_stats` — rejected: thinner, per-event rather than per-day
consolidated, and not the canonical learning record.

### D2 — Per-session opt-in flag + frozen window (the fourth knob)
Add `learning_feedback_enabled: bool` (non-nullable, server default false) and
`learning_feedback_window: int | None` (nullable, meaningful only when the flag is
on) to `PaperTradingSession`, mirroring the `stop_loss_enabled`/`stop_loss_pct`
pair. Thread both through `AIBuildParams` (`to_dict`/`from_payload`), persist them in
`flows/build.py`, accept them on the AI build request schema (flag default false,
window optional), and expose both on the session read. When the flag is on and no
window is supplied, default the window to `LEARNING_FEEDBACK_DEFAULT_WINDOW` (same
"configured default fills the frozen param" behavior as `stop_loss_pct`).
*Alternatives rejected:* (a) **global-only setting / global env window** — a global
switch or window applies retroactively and inconsistently across a portfolio's life,
defeating cross-session comparison; the user explicitly wanted the window to be a
build-time choice, not a static env variable; (b) **per-session but live-toggleable
(PUT endpoint)** — switching it on/off (or re-depthing it) mid-session makes two
sessions incomparable and muddies the strategy identity. A new migration adds both
columns (`learning_feedback_enabled` server default false, backfilled to false;
`learning_feedback_window` nullable).

### D3 — New requirement(s), not a modification of the prompt requirement
Model this as **ADDED** requirements ("Learning feedback is a per-session opt-in
frozen at build time" and "Rebalance agent informed of recent prior-run outcomes")
rather than editing an existing prompt requirement. It is a distinct,
independently-testable behavior and keeps the existing prompt requirements
(transaction-cost, trend-strategy, unallocated-cash, crypto-scoped) intact. The
`app-shell` build-form and session-detail requirements are **MODIFIED** to add the
opt-in control and the session-detail indicator, the same way the guardrail and
stop-loss changes extended them.

### D4 — Read helper placement and shape
Add `list_daily_run_snapshots(session, session_id, limit)` to
`paper_trading/service.py`, mirroring `get_daily_run_snapshot`. Order by
`run_date DESC`, `LIMIT` the window; return the model rows (callers read
`.document` / `.run_date`). Read-only, no new indexes (the existing unique
`(session_id, run_date)` supports the ordered scan). *Alternative:* a bespoke
projection/aggregate query — rejected: premature; N is small (~5) and the
distillation already lives in a pure helper.

### D5 — Distillation is a pure, cost-forward helper in `agent.py`
Add a pure function (e.g. `_summarize_recent_outcomes(snapshots) -> str | None`)
beside `_build_rebalance_input`. It maps each snapshot `document` to one compact
**cost/churn-forward** line: lead with net-of-fees realized P&L (the run's gross
`realized_pnl` minus the day's `fees_total`), then the fees paid and the order/churn
count, then end-of-day valuation and — when present — the day return and gate/skip
counts. The fees come from the document's `fees_total` (and per-order `fee`)
persisted via D8, so "fees paid" and the net figure are exact rather than
approximated; a day predating per-order fee recording simply reads a zero/absent
`fees_total` (net then equals gross, with fees shown as 0). It defensively tolerates
missing keys (the document schema has evolved over time) and returns `None` for an
empty list so the caller omits the section. `_build_rebalance_input` gains an optional
`recent_outcomes` parameter (default empty/omitted) and appends the rendered section
only when non-empty — preserving a byte-identical prompt otherwise. The cost-forward
framing is deliberate: the agent's known failure mode is churn whose fees erode
returns, so net-of-fees P&L and fees paid lead the line.

### D6 — Fetch gated in the flow by the per-session flag, using the frozen window
`run_rebalance_event` fetches outcomes only when the session's
`learning_feedback_enabled` is true; it reads the session's frozen
`learning_feedback_window` (falling back to `LEARNING_FEEDBACK_DEFAULT_WINDOW` only
if an enabled legacy row somehow has a null window), calls
`list_daily_run_snapshots(..., limit=window)`, and passes the rows to
`_build_rebalance_input`. Otherwise it fetches nothing and passes an empty window.
This keeps the "disabled ⇒ no DB read, no prompt change" guarantee at the flow
boundary. Applies to both the standard and crypto-scoped rebalance paths, which
share `_build_rebalance_input`.

### D7 — Setting is the build-time default/fallback only, not a runtime knob
New `LEARNING_FEEDBACK_DEFAULT_WINDOW: int = 5` in `config.py` (pydantic-settings
singleton), consistent with the `STOP_LOSS_DEFAULT_PCT` / `GUARDRAIL_DEFAULT_*`
settings. It pre-fills the build-form window control and fills the frozen window when
a session opts in without specifying one; it is **not** read at rebalance time
(rebalance always reads the session's frozen `learning_feedback_window`). There is no
global env window and no global kill switch — per the user's decision the window is a
build-time choice, so each session's depth is part of its fixed, comparable identity.
Default 5 ≈ a trading week of context. Build-request validation requires a positive
window when the flag is on (a non-positive/empty value falls back to the default
rather than disabling — enable/disable is solely the flag).

### D8 — Persist the per-trade fee so "fees paid" is exact
The cost-forward distillation promises an explicit **fees paid** figure and a
**net-of-fees** realized P&L, but under the current fee model that figure cannot be
cleanly derived after the fact from the daily-run document: equities are free,
crypto is `CRYPTO_FEE_PCT × notional`, the document's `realized_pnl` is gross, and
the order document carries no asset class. Rather than reconstruct fees by
re-deriving each order's asset class, persist the fee at its source: add a `fee`
column to `PaperTrade` and set it in `record_trade` — the single choke point that
*already computes* the asset-class-aware fee it adds to the session's cumulative
`total_fees`. `_order_document` then surfaces each order's `fee`, and
`_build_run_document` records the day's `fees_total` (sum of the day's order fees)
in the learning document, so the distillation reads an exact per-day cost.
*Alternatives rejected:* (a) **reframe the distillation to net P&L + churn count
only** (no explicit fees) — rejected by the user, who wants fees shown explicitly;
(b) **recompute fees at assembly time** by joining each trade to its asset's
category — fragile (depends on the asset row still existing and its category being
stable) and duplicates the fee formula away from its choke point;
(c) **put the day's fees in `run_stats`** — thinner (run-days only, no per-order
granularity) and couples the figure to the run-stats shape. The column is
non-nullable with a `0` server default; trades recorded before it default to `0`
and are **not** backfilled (historical days show `fees_total = 0`), which the user
accepted. This does not change the session's cumulative `total_fees` or the net
valuation — only where the already-charged per-trade fee is recorded.

## Risks / Trade-offs

- **Document schema drift** (keys added/removed across the snapshot's history) →
  the distillation reads defensively with `.get(...)` and omits any field it
  cannot find; a malformed/empty document contributes no line rather than raising.
- **Prompt bloat / token cost** → the window is small (default 5) and each
  snapshot renders to a single compact line; the per-session flag disables entirely.
- **Determinism of tests** → distillation is pure and fed fixed snapshot fixtures;
  the "disabled / no history" path asserts the section is absent.
- **Agent over-anchoring on recent noise** → the block is explicitly advisory and
  adds no constraints; sizing/guardrails are untouched, bounding the blast radius.
- **Window is fixed for the session's life** → accepted and intended: both whether a
  session learns and how deeply are frozen so sessions stay comparable (the user's
  explicit reason); re-depthing requires building a new session, exactly like
  changing a stop-loss threshold.

## Migration Plan

One Alembic migration adds `learning_feedback_enabled` (non-nullable, `false` server
default, backfilled to false) and `learning_feedback_window` (nullable) to
`paper_trading_sessions`, so existing sessions behave exactly as today (learning
off), plus `fee` (non-nullable, `0` server default, backfilled to 0) to
`paper_trades` (D8), so existing trades show no recorded fee until re-recorded.
`down_revision` = current head; round-trip verified with upgrade/downgrade.
Beyond that there is no runtime config to flip — newly built sessions default OFF and
choose their own window at build. Rollback = downgrade the migration (and remove the
build-form controls); nothing to undo in data.

## Open Questions

None.
