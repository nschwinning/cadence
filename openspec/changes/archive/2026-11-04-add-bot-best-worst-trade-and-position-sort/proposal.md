## Why

The bot detail page shows aggregate performance KPIs but no sense of which individual trades drove them — a user cannot tell at a glance whether a bot's realized P&L came from one big winner or many small gains. And the open-positions table is locked to a single sort order (by ticker), so there is no way to see which positions were opened most recently. Both are small, self-contained readability improvements the user asked for.

## What Changes

- Add a **best / worst trade** figure to the per-session performance KPIs: the single closed round-trip with the highest realized P&L and the one with the lowest. Each carries its ticker and realized P&L. Surfaced through the existing `/kpis` endpoint and rendered as a tile in the Performance section of the bot detail page. Computed on read from the existing trade ledger — no new table or migration.
- Add a **sort control** to the open-positions table on the bot detail page: sort by ticker (the current default) or by opened timestamp. Frontend-only re-sort of the already-loaded positions; the API payload is unchanged.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `strategy-bots`: the per-session performance-KPI read additionally reports the session's best and worst closed round-trip trade (ticker + realized P&L), derived from the recorded trade ledger.

## Impact

- Backend: `strategy_bots/service.py` (new best/worst round-trip computation reused by `bot_session_kpis`; `BotKpis` dataclass gains best/worst fields), `api/schemas.py` (`BotKpisRead` gains the fields). No change to the trade ledger model, tick/exit logic, snapshots, or migrations.
- Frontend: `BotSessionPage.tsx` (best/worst trade tile in the Performance section; sort control on the open-positions table), `types/api.ts` (`BotKpis` gains the new fields). No change to `BotsPage` or the list endpoint.
- The open-positions sort is purely client-side; the `/sessions/{id}` payload and its backend `order_by` default are untouched.
