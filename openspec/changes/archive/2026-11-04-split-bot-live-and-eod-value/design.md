## Context

Two value cadences already exist for a bot session:

- **Daily snapshots** (`bot_value_snapshots`): one row/day, written by the 16:15 ET snapshot job. Fields: `snapshot_date: date`, `total_value`, `realised_pnl`, `unrealised_pnl`, `created_at: datetime` (actual capture time). Marked-to-market at capture.
- **Intraday value points** (`bot_value_points`): one row per bot tick (~5 min), marked-to-market, 30-day retention. Fields: `captured_at: datetime`, `total_value`, `realised_pnl`, `unrealised_pnl`.

Today `bot_session_kpis` (`service.py:1037`) and `bot_current_value` (`service.py:975`) read current value from `snapshots[-1].total_value` only, so between snapshots the tile is pinned to the prior EOD close while the 5m/1h chart (reading value points) moves — the reported "lag". Both tables carry the same marked-to-market `(total_value, realised_pnl, unrealised_pnl)` triple with a real timestamp, so "take the most recently captured observation" is a clean, deterministic rule with no new broker calls.

## Goals / Non-Goals

**Goals:**
- Report a **live value** (freshest observation) and a separate **end-of-day value** (latest daily snapshot) on both the detail KPIs and the overview list.
- Keep the detail Performance grid at 12 tiles by splitting the value tile in two and dropping the redundant "Allocated capital" tile.
- Remove the mislabeled hardcoded `FreshnessBadge kind="live"` from the Performance section.

**Non-Goals:**
- No live broker/quote fan-out per read (explicitly not chosen). No change to the value-history/chart endpoint, the intraday capture/retention job, the daily snapshot job, trade ledger, sizing, or tick. No migration/new table. Paper-trading page badges unchanged.

## Decisions

- **`latest_value_observation(session, bot) -> ValueObservation | None`** (new, in `service.py`): returns the more recent of {latest `bot_value_point` by `captured_at`, latest `bot_value_snapshot` by `created_at`} as a small dataclass `(total_value, realised_pnl, unrealised_pnl, as_of: datetime, is_intraday: bool)`; `None` when the session has neither. Timestamps compared in UTC; on an exact tie (practically impossible) the intraday point wins. Reuses `list_bot_snapshots` and a latest-point query mirroring `list_bot_value_history`'s ordering.
- **`bot_current_value`** becomes the single source of the **live value**: returns `latest_value_observation(...).total_value`, else cost-marked `total_value(bot, {})`. Used by both the detail KPI and the overview column.
- **End-of-day value** is a thin accessor over `list_bot_snapshots(...)[-1].total_value`, or `None` when there are no snapshots. (It is the latest snapshot specifically, independent of any newer intraday point.)
- **`bot_session_kpis`**: `current_value` and `unrealised` come from the observation (cost-mark fallback with unrealised 0.0 and `as_of=None` when `None`); `total_return`/`total_return_pct` continue to derive from `current_value` (now the live value). New dataclass fields `eod_value: float | None`, `value_as_of: datetime | None`, `value_is_intraday: bool`.
- **Schemas**: `BotKpisRead` gains `eod_value: float | None = None`, `value_as_of: datetime | None = None`, `value_is_intraday: bool`. The existing `allocated_capital` field stays in the payload (still consumed by the header); only the tile is removed. `BotSessionRead` gains `eod_value: float | None` (populated by the router `_to_read` helper from the new EOD accessor).
- **Frontend detail (`BotSessionPage.tsx`)**: replace the "Current value" tile with a **"Live value"** tile (value `current_value`, hint derived from `value_as_of` / `value_is_intraday`, e.g. an as-of time or "End-of-day basis") and add an **"End of day value"** tile (`eod_value`, or `—` with a "Needs a daily snapshot" hint when null); remove the "Allocated capital" tile; remove `<FreshnessBadge kind="live" />` from the section header. Grid stays 12 tiles.
- **Frontend overview (`BotsPage.tsx`)**: rename the "Current value" column header to **"Live value"** (still `bot.current_value`, now freshest) and add an **"End of day"** column (`bot.eod_value`, `—` when null).
- **`types/api.ts`**: `BotKpis` gains `eod_value: number | null`, `value_as_of: string | null`, `value_is_intraday: boolean`; the bot session read type gains `eod_value: number | null`.

## Risks / Trade-offs

- **Clock skew between the two tables**: `created_at` (snapshot) and `captured_at` (point) must be comparable UTC datetimes; both are DB-defaulted tz-aware timestamps, so comparison is direct. Right after the 16:15 job the snapshot wins (correct); during the next session the intraday points win (correct).
- **"Live value" is a ~5-min-old mark, not a real-time quote.** The tile hint uses `value_as_of` so the figure is honest about its age rather than implying a live quote.
- **Overview cost of the extra value**: `bot_current_value` already runs per listed session; the EOD accessor reuses the same already-loaded snapshots, so no extra per-session query is introduced beyond the existing snapshot read.
