## Why

On the bot detail page the "Current value" performance tile differs a lot from the value chart, and the user reported it appears to lag. It does: `bot_session_kpis` and `bot_current_value` derive current value from the latest **daily** `bot_value_snapshots` row, written once per day by the 16:15 ET snapshot job. Intraday that figure is pinned to the prior end-of-day close and never moves, while the value chart at 5m/1h reads `bot_value_points` captured marked-to-market on every bot tick (~5 min). The tile and the intraday chart therefore only agree at 1D resolution.

Rather than silently swap the snapshot value for the intraday one, the clearer fix is to show **both**: a freshest-mark **live value** and the **last end-of-day value**, side by side — on the detail tiles and in the bots overview. Secondarily, the Performance section renders a hardcoded green `FreshnessBadge kind="live"` that is a mislabel (those tiles were snapshot-based, not live); with two self-describing value tiles that badge is no longer needed.

## What Changes

- **Backend KPIs:** the bot session's current value (and its unrealised P&L) now reflect the most recently captured value observation — the latest `bot_value_point` when it is newer than the latest daily snapshot, else the latest snapshot, else cost-marked `total_value(bot, {})`. This is the **live value**. The read additionally exposes a separate **end-of-day value** (the latest daily snapshot's total value, or null when no snapshot exists yet) plus the live value's as-of timestamp and whether it came from an intraday point. No new broker/quote calls.
- **Bot detail performance tiles:** the single "Current value" tile becomes two tiles — "Live value" (freshest mark, with an as-of hint) and "End of day value" (latest snapshot). To keep the grid at 12 tiles (3×4) the redundant "Allocated capital" tile is removed (it is already shown in the header facts as "Capital"). The hardcoded "Live" `FreshnessBadge` on the Performance section is removed; the two tiles now describe their own freshness.
- **Bots overview:** the "Current value" column is renamed "Live value" (now the freshest mark) and a new "End of day" column is added beside it.

## Capabilities

### Modified Capabilities
- `strategy-bots`: the "Bot value snapshots and performance KPIs" requirement now defines current value / unrealised P&L from the freshest value observation and exposes a separate end-of-day value with an as-of timestamp; the "Session-list current value" requirement now exposes both a live and an end-of-day value; the "Bot detail performance tiles" requirement now shows distinct live and end-of-day value tiles, drops the allocated-capital tile, and no longer claims a single live freshness for the section.

## Impact

- Backend: `strategy_bots/service.py` (new `latest_value_observation` helper; `bot_current_value`, a new end-of-day value accessor, and `bot_session_kpis` reworked; `BotKpis` dataclass gains `eod_value`, `value_as_of`, `value_is_intraday`), `strategy_bots/schemas.py` (`BotKpisRead` + `BotSessionRead` gain the new fields), router `_to_read` helper populates the overview end-of-day value.
- Frontend: `types/api.ts` (`BotKpis`, bot session read gain the new fields), `pages/bots/BotSessionPage.tsx` (split value tiles, drop allocated-capital tile, remove the Performance `FreshnessBadge`), `pages/bots/BotsPage.tsx` (rename column + add end-of-day column).
- No database migration (both `bot_value_snapshots` and `bot_value_points` already exist). No change to the value-history/chart endpoint, the intraday capture/retention job, the daily snapshot job, trade ledger, sizing, or tick. The paper-trading page's own freshness badges are unchanged.
