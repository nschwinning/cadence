## Context

`BotValueChart` plots `bot_value_snapshots`, keyed by `snapshot_date` (a `Date`) and
written only by the daily snapshot cron (`service.py` ~line 575). The five-minute tick
(`_tick_session`) already computes `marks = {ticker: bars[-1].close}` and can derive each
session's total value, but it persists nothing. To offer 5-minute/hourly/daily/monthly
resolutions we must (a) capture intraday value going forward and (b) teach the read side
to serve any resolution on one point shape.

## Goals

- Capture a timestamped value point per processed session on each tick (forward-only).
- Serve `5min`/`hourly`/`daily`/`monthly` from a resolution-aware read, reusing existing
  daily snapshots for the coarse grains so pre-intraday history is preserved.
- Render any resolution with a single chart on a time x-axis plus a resolution switcher.

## Decisions

### New `bot_value_points` table (not a column on snapshots)

Intraday points are a different grain (timestamp, many-per-day) than
`bot_value_snapshots` (one-per-date). A new table keeps the daily snapshot semantics and
its unique-per-date upsert intact.

Columns: `id` (uuid pk), `bot_session_id` (fk → `bot_sessions`, indexed),
`captured_at` (timestamptz), `total_value`, `realised_pnl`, `unrealised_pnl` (floats).
Index on `(bot_session_id, captured_at)` for range/order queries. One Alembic migration
adds the table; no change to existing tables.

### Capture inside `_tick_session`, forward-only, best-effort

Right after a session's marks/total value are known for the tick, insert one
`BotValuePoint` stamped with the tick time. Only sessions actually processed get a point
(market-closed ticks process nothing → no points), satisfying "no points when nothing is
processed". No backfill: existing sessions start accruing intraday points from the first
tick after deploy; `5min`/`hourly` read empty until then (daily/monthly stay full from
snapshots). Capturing must not alter position/ledger outcomes — persist the point without
coupling it to the order path.

### Resolution-aware read with downsampling

`resolution` is a `str` enum query param (`5min|hourly|daily|monthly`), validated by a
Pydantic/`Enum` so an unknown value yields `422` automatically. Mapping:

| resolution | source | shaping |
|---|---|---|
| `5min`    | `bot_value_points` | raw points, oldest first |
| `hourly`  | `bot_value_points` | last point per `date_trunc('hour', captured_at)` |
| `daily`   | `bot_value_snapshots` | each snapshot → point at end-of-day timestamp |
| `monthly` | `bot_value_snapshots` | last snapshot per calendar month → point |

Downsampling ("last within bucket") is done deterministically — prefer SQL
(`DISTINCT ON (bucket) ... ORDER BY bucket, captured_at DESC`) but a small in-Python
reduce is acceptable and unit-testable. Daily/monthly map `snapshot_date` → a timestamp
(end-of-day ET) so every resolution shares the timestamped point shape.

### Uniform timestamped point shape

Response: `{ resolution, items: [{ timestamp, total_value, realised_pnl,
unrealised_pnl }], total }`. `timestamp` is ISO-8601. The frontend renders one series
off `timestamp` regardless of resolution (x-axis is already `type: 'time'`).

### Frontend: resolution switcher + timestamped series

`BotValueChart` gains a segmented control (5m / 1h / 1D / 1M) whose selection is
component state fed into the history query (resolution in the query key → per-resolution
cache). The series builder keys off `timestamp` instead of `snapshot_date`. Daily/monthly
keep the existing carry-forward-to-today behaviour; intraday resolutions plot the raw
timestamped points without cross-session-gap carry-forward (overnight gaps should read as
gaps, not flat lines). Default resolution: `daily` (preserves today's view). The
"not enough history" placeholder still shows when a resolution has < 2 points.

### Intraday retention: keep the last 30 days

Raw `bot_value_points` are pruned to the most recent 30 days to bound storage. Pruning
runs inside the once-daily snapshot job (`run_bot_snapshots`) — it already runs daily and
touches every session, so it is the natural home — as a single
`DELETE FROM bot_value_points WHERE captured_at < now() - interval '30 days'` across all
sessions. The window is a config constant (e.g. `BOT_VALUE_POINT_RETENTION_DAYS = 30`).

Consequence: `5min` and `hourly` both read from the raw points, so **both** are bounded to
~30 days; `daily`/`monthly` come from `bot_value_snapshots` and stay unbounded. If a longer
hourly history is wanted later, it would need a separate hourly rollup table retained
beyond 30 days — out of scope here.

## Risks / Trade-offs

- **Storage growth:** bounded by the 30-day retention above — at ~78 points per bot per
  market day, a session holds on the order of a couple thousand intraday rows at steady
  state.
- **Hourly inherits the 30-day window** since it is derived from the raw points (not a
  separate rollup); acceptable, and called out in the spec.
- **Forward-only gap:** existing sessions show empty 5-min/hourly charts until ticks
  accrue; mitigated by defaulting the switcher to `daily` and messaging the empty state.
- **Capture in the trading path:** adding a write to `_tick_session` must not change
  trade outcomes; keep it additive and after the trading decisions for the session.

## Migration

One Alembic migration creating `bot_value_points` with its index. No data migration, no
change to existing tables. Reversible (drop table).
