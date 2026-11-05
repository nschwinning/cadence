## Context

See proposal.md — Why. On the dashboard leaderboard the "Value" column is advertised as live (marked-to-market, 30s refetch) and that holds for AI rows but not strategy-bot rows. The bot adapter `dashboard_performance` in `backend/src/cadence/strategy_bots/service.py` derives the row's point-in-time value from `snapshots[-1].total_value` — the latest **daily** `bot_value_snapshots` row written once/day — so a bot's leaderboard value is pinned to the prior end-of-day close between snapshots.

The freshest-value path already exists and is already used on the bots list/detail pages: `latest_value_observation(session, bot)` returns the more recent of {latest intraday `bot_value_point` by `captured_at`, latest daily `bot_value_snapshot` by `created_at`} (intraday wins exact ties), carrying a consistent marked-to-market `unrealised_pnl`; `bot_current_value` returns its `total_value`, else cost-marked `total_value(bot, {})`. Only the dashboard adapter was missed.

## Goals / Non-Goals

**Goals:**
- A bot row's reported `current_value` (and `unrealised_pnl`) on the overview is the session's freshest captured value observation, so bot and AI rows are live on the same basis.
- Reuse the existing `latest_value_observation` / `bot_current_value` path — no new query, no migration, no broker/quote fan-out.

**Non-Goals:**
- No change to the plotted value **series** (`points`) or the combined-equity line — it stays end-of-day daily snapshots for both kinds.
- No change to the range-start baseline `value_start`, `contributions`, the benchmark value, `realised_pnl`/`fees`, or the `kind='bot'` tag.
- No change to the AI adapter, the endpoint shape, the snapshot/intraday jobs, or any frontend component.

## Decisions

**Source the headline value from the freshest observation, not the latest snapshot.** In `dashboard_performance`, replace the `snapshots[-1].total_value` / `snapshots[-1].unrealised_pnl` assignment that sets `current_value`/`unrealised` with `latest_value_observation(session, bot)`: when present use its `total_value`/`unrealised_pnl`, else fall back to cost-marked `total_value(bot, {})` with `unrealised = 0.0`. *Alternative considered:* add a dedicated "live value" field alongside the snapshot value and let the frontend choose — rejected: the leaderboard already renders `current_value` as the live column, and AI rows already put their live value there, so the fix belongs in the one field both kinds share, keeping the two row kinds symmetric with zero frontend change.

**Keep the value series end-of-day.** Only the point-in-time `current_value`/`unrealised` become live; `points` (and thus the combined-equity overlay and `value_start` baseline) stay sourced from daily snapshots. *Why:* the chart plots a daily time series for both kinds; mixing an intraday "now" point into a daily series would be inconsistent with AI rows, whose series is also daily. The headline number being fresher than the last plotted point matches how AI rows already behave.

**Let range `pnl` follow the live value.** `pnl = current_value - value_start` therefore tracks the live `current_value`. This is intentional and matches AI rows, whose range P/L is likewise live-value-minus-range-start-baseline. No separate reconciliation is needed.

## Risks / Trade-offs

- [The headline live value can exceed the last plotted series point, so the leaderboard number and the chart's last daily point differ intraday] → This already happens for AI rows and is the intended "live vs end-of-day" distinction; the series stays daily for both kinds, so the two row kinds behave identically. No mitigation needed beyond parity with AI rows.
- [A bot with neither snapshots nor value points reports a cost-marked value with zero unrealised] → Unchanged from today's cost fallback; preserves existing behavior for brand-new bots.
