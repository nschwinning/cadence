## Why

The dashboard leaderboard's "Value" column is advertised as live — a green dot with the tooltip "Live — marked to market against current quotes" — and the overview refetches every 30s. That claim holds for **AI paper-trading** rows (their value comes from `session_kpis(...).current_value`, which marks open positions to market via the broker) but **not** for **strategy-bot** rows. The bot adapter `dashboard_performance` derives its value from `snapshots[-1].total_value` — the latest **daily** `bot_value_snapshots` row written once/day by the 16:15 ET job — so between snapshots a bot's leaderboard value is pinned to the prior end-of-day close while an AI portfolio beside it moves live.

The freshest-value path already exists and is already used elsewhere: `latest_value_observation` / `bot_current_value` return the most recently captured observation (the latest intraday `bot_value_point` when newer than the latest daily snapshot, else the snapshot, else cost-marked), and they already feed `BotSessionRead.current_value` on the bots list and detail pages. Only the dashboard adapter was missed. The fix is to point it at the same live value so bot and AI rows are live on the same basis.

## What Changes

- **Backend dashboard adapter:** `dashboard_performance` sources the bot row's point-in-time `current_value` and `unrealised_pnl` from the most recently captured value observation (`latest_value_observation`) — latest intraday value point when newer than the latest daily snapshot, else the latest snapshot, else cost-marked `total_value(bot, {})` with unrealised `0.0` — instead of the latest daily snapshot. The range `pnl = current_value − value_start` therefore becomes live, matching how AI rows already behave.
- **Unchanged:** the daily-snapshot value **series** (`points`) plotted on the combined-equity line (still end-of-day for both kinds), the range-start baseline `value_start`, the opening `contributions`, the benchmark value, `realised_pnl`/`fees`, and the `kind='bot'` tag.
- **No frontend change:** the leaderboard already renders `s.current_value` uniformly and `aggregate.ts` already sums it uniformly, so bot rows become live purely from the backend payload.

## Capabilities

### Modified Capabilities
- `dashboard`: the "Per-session performance data for the overview" requirement now defines each session's reported current value (and unrealised P&L) as the session's live/most-recent value on a per-kind basis — AI sessions marked-to-market via the broker (unchanged), strategy-bot sessions taken from the most recently captured value observation rather than the latest daily snapshot — so bot and AI rows carry live values on the same basis.

## Impact

- Backend: `strategy_bots/service.py` `dashboard_performance` only (reuses the existing `latest_value_observation`). No change to the AI adapter, the dashboard endpoint shape, the value series / combined-equity basis, the daily snapshot job, the intraday capture/retention job, range-pnl baseline semantics, benchmark math, or the automation/activity/universe sections.
- Frontend: none expected (the leaderboard renders `current_value` as-is).
- No database migration (both `bot_value_snapshots` and `bot_value_points` already exist). No broker/quote fan-out for bots — "live" for a bot means its freshest captured value observation, exactly as on the bots list/detail.
