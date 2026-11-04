## Why

A strategy bot ticks every five minutes during market hours, but its value chart shows
only **daily** end-of-day points. The `BotValueChart` plots `bot_value_snapshots`, which
are keyed by `snapshot_date` (a date) and written solely by the daily snapshot cron — the
five-minute tick persists no value at all. So the equity curve is far coarser than the
data the bot actually acts on, and there is no way to see intraday movement or to zoom
out to a longer-horizon view.

Users want to view the bot's value at selectable resolutions — **5-minute, hourly,
daily, and monthly** — and switch between them on the chart.

## What Changes

- **Intraday capture (forward-only):** each tick persists a timestamped value point
  (total value, realised and unrealised P&L) for every active session it processes, in a
  new `bot_value_points` table. Existing daily snapshots are unchanged, so daily/monthly
  history that predates intraday capture stays intact. No backfill — intraday history
  accrues from the first tick after this ships.
- **Multi-resolution reads:** the value-history endpoint accepts a `resolution`
  parameter (`5min`, `hourly`, `daily`, `monthly`). `5min` returns raw intraday points;
  `hourly` downsamples intraday points to the last point per hour; `daily` returns the
  existing daily snapshots; `monthly` returns the last snapshot per calendar month. Every
  resolution returns points on a **uniform timestamped shape** so one chart renderer
  serves them all. An unknown resolution returns `422`; an unknown session returns `404`.
- **Intraday retention (30 days):** the once-daily snapshot job prunes raw intraday points
  older than 30 days so storage stays bounded. Because `5min` and `hourly` both read from
  the raw points, both are bounded to ~30 days; `daily`/`monthly` (from daily snapshots)
  stay unbounded.
- **Chart resolution switcher:** the bot detail chart gains a control to pick the
  resolution and refetches accordingly, rendering on a time x-axis.

## Capabilities

### Modified Capabilities
- `strategy-bots`: the tick now also persists an intraday value point per processed
  session, and the value-history read exposes selectable resolutions over a uniform
  timestamped point shape.

## Impact

- Backend: new `BotValuePoint` model + Alembic migration; `strategy_bots/service.py`
  (capture at tick in `_tick_session`, resolution-aware history query + downsampling);
  `api/routers/bots.py` (`resolution` query param on value-history); `api/schemas.py`
  (timestamped point + resolution in the response).
- Frontend: `pages/bots/BotValueChart.tsx` (resolution switcher + timestamped series),
  `api/bots.ts` and `types/api.ts` (resolution param + point shape).
- Storage: ~78 intraday points per bot per market day, bounded by a 30-day retention
  window (pruned by the daily snapshot job); `BOT_VALUE_POINT_RETENTION_DAYS = 30` config.
