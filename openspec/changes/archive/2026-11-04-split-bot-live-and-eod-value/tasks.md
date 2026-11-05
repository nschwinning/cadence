## 1. Backend — value observation + KPIs

- [x] 1.1 Add a `ValueObservation` dataclass and `latest_value_observation(session, bot) -> ValueObservation | None` to `strategy_bots/service.py`: pick the more recent of {latest `bot_value_point` by `captured_at`, latest `bot_value_snapshot` by `created_at`}, comparing in UTC (intraday wins exact ties); return `None` when the session has neither. Reuse `list_bot_snapshots` and a latest-point query mirroring `list_bot_value_history`'s ordering.
- [x] 1.2 Rework `bot_current_value` to return the observation's `total_value` (the live value), falling back to cost-marked `total_value(bot, {})` when the observation is `None`.
- [x] 1.3 Add an end-of-day value accessor (latest daily snapshot `total_value`, else `None`).
- [x] 1.4 Rework `bot_session_kpis`: set `current_value` and `unrealised` from the observation (cost-mark fallback with unrealised 0.0 and `value_as_of=None` when `None`); add `eod_value`, `value_as_of`, `value_is_intraday` to the `BotKpis` dataclass; keep `total_return`/`total_return_pct` derived from `current_value`.
- [x] 1.5 `strategy_bots/schemas.py`: add `eod_value: float | None = None`, `value_as_of: datetime | None = None`, `value_is_intraday: bool` to `BotKpisRead`; add `eod_value: float | None` to `BotSessionRead`. Populate `BotSessionRead.eod_value` in the router `_to_read` helper from the new accessor.

## 2. Frontend — tiles, overview columns, types

- [x] 2.1 `types/api.ts`: add `eod_value: number | null`, `value_as_of: string | null`, `value_is_intraday: boolean` to `BotKpis`; add `eod_value: number | null` to the bot session read type.
- [x] 2.2 `pages/bots/BotSessionPage.tsx`: replace the "Current value" tile with a "Live value" tile (value `current_value`, hint from `value_as_of`/`value_is_intraday`); add an "End of day value" tile (`eod_value`, or `—` + "Needs a daily snapshot" when null); remove the "Allocated capital" tile; remove `<FreshnessBadge kind="live" />` from the Performance section header (grid stays 12 tiles).
- [x] 2.3 `pages/bots/BotsPage.tsx`: rename the "Current value" column header to "Live value"; add an "End of day" column rendering `bot.eod_value` (`—` when null).
- [x] 2.4 Per-tile freshness badges: add an optional `badge` prop to the shared `StatTile` (rendered beside the label); add a `TileFreshnessBadge` (`live`/`eod`) to `BotSessionPage.tsx` and a `valueFreshness(kpis)` helper; badge every performance tile — snapshot-derived tiles (end-of-day value, maximum drawdown, Sharpe ratio, benchmark) as `eod`, current/marked-to-market tiles (available cash, realised P&L, best/worst trade, total trades) as `live`, and the observation-derived tiles (live value, total return, unrealised P&L) via `valueFreshness`; forward `badge` through `TradeExtremeTile`/`BenchmarkTile`.

## 3. Tests & verification

- [x] 3.1 Backend unit tests (`strategy_bots`): `latest_value_observation`/`bot_current_value`/`bot_session_kpis` prefer a newer intraday point over an older snapshot, prefer the snapshot when it is at least as recent (post-EOD / no point), use the observation's unrealised P&L, and fall back to cost-mark (unrealised 0, `value_as_of` None) with no data; `eod_value` equals the latest snapshot or is None; `value_is_intraday` true/false accordingly; KPI API serializes `eod_value`/`value_as_of`/`value_is_intraday` and the session list serializes `eod_value`.
- [x] 3.2 Frontend tests: detail Performance section shows "Live value" and "End of day value" tiles, no "Allocated capital" tile, and no section-level freshness badge; the end-of-day tile shows a placeholder when `eod_value` is null; overview renders both "Live value" and "End of day" columns. Per-tile badges: each tile carries a `tile-freshness-live`/`tile-freshness-eod` badge (snapshot tiles EOD, marked-to-market tiles live); observation-derived tiles flip to `eod` when `value_is_intraday` is false.
- [x] 3.3 Run gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`; `cd frontend && npx vitest run && npx tsc --noEmit`.
- [x] 3.4 `openspec validate split-bot-live-and-eod-value --strict`.
