## Why

The bot detail page shows "Current value" and "Allocated capital" as KPI tiles but never surfaces how much free cash the bot is holding as a headline figure, so a user can't tell at a glance how much is deployed versus idle. And the bots overview lists each session's static allocated capital (its fixed return baseline), not its live current value — the figure a user actually scans the list for when comparing how bots are doing right now.

## What Changes

- Add an "Available cash" KPI tile to the bot detail page's Performance section, sourced from the session's free cash (`bot.cash`). This requires the per-session KPI read to carry a `cash` figure.
- On the bots overview (list) page, show each session's **current value** in place of its allocated capital. This requires the session-list read to carry a `current_value` figure (marked from the same source the detail KPI uses).
- Frontend: render the new tile on the detail page and swap the overview capital column to current value (column header updated accordingly).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: the per-session performance KPI read now includes the session's available (free) cash; the session-list read now includes each session's current (marked-to-market) value.

## Impact

- Backend: `BotKpis` dataclass + `bot_session_kpis` (`strategy_bots/service.py`) gain a `cash` field; `BotKpisRead` schema gains `cash`. `BotSessionRead` schema gains `current_value`; `list_bot_sessions` (`api/routers/bots.py`) populates it per row from the session's latest value snapshot (cost-basis fallback when no snapshot exists), reusing the detail KPI's current-value definition.
- Frontend: `BotSessionPage.tsx` renders an "Available cash" tile; `BotsPage.tsx` renders `current_value` instead of `allocated_capital`; `types/api.ts` mirrors the new `cash`/`current_value` fields.
- No migration, no new table, no change to tick/snapshot/sizing/notifications/value-history, and no change to how the detail KPI computes current value (only reused on the list).
