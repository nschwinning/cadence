## Why

The bot detail page's Performance section carries a "Transaction fees" KPI tile that is always $0 for paper-trading bots — pure dead weight. Meanwhile the bot has a configured benchmark index but the detail page never shows how the bot is actually doing *against* it (the benchmark only surfaces in the daily notification and the dashboard overlay). Swapping the dead fees tile for a benchmark-comparison tile puts a meaningful, already-computable figure where an empty one used to be.

## What Changes

- Add benchmark comparison figures to the per-session bot KPI read (`BotKpis` / `BotKpisRead`): the benchmark id, the benchmark's since-inception buy-and-hold return fraction, and the session's excess return fraction (bot total return − benchmark return). All `None` when the session has no snapshots yet or the benchmark lacks usable stored closes — mirroring the existing paper-trading KPI contract and the bot's own daily-notification benchmark suffix.
- Factor the benchmark load/compute shared by `bot_session_kpis` and `_bot_benchmark_suffix` into one helper so both agree (notification output stays byte-identical).
- On the bot detail page Performance grid, **replace** the "Transaction fees" tile with a single benchmark-comparison tile: primary figure is the excess return %, sub-label is the benchmark's own return %, headed "vs {benchmark name}". A 1-for-1 swap, so the grid layout is unchanged. Em-dash fallback when the comparison is unavailable.
- Keep the backend `total_fees` KPI field (the daily snapshot notification still reads it); only the frontend tile is removed.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `strategy-bots`: the per-session KPI read now includes the benchmark return and excess return, and the detail Performance section shows a benchmark-comparison tile in place of the transaction-fees tile.

## Impact

- Backend: `backend/src/cadence/strategy_bots/service.py` (`BotKpis` dataclass, `bot_session_kpis`, `_bot_benchmark_suffix` refactor to share a helper); `backend/src/cadence/api/schemas.py` (`BotKpisRead`).
- Frontend: `frontend/src/types/api.ts` (`BotKpis` interface); `frontend/src/pages/bots/BotSessionPage.tsx` (Performance grid tile swap).
- No new migration/table, no API route changes, no change to the value chart, dashboard adapter, notification wording, or tick/snapshot/sizing/trade-ledger logic.
