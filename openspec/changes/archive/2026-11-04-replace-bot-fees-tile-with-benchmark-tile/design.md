## Context

See `proposal.md` — Why. The strategy-bots subsystem already computes a since-inception
buy-and-hold benchmark comparison for its daily notification (`_bot_benchmark_suffix` in
`strategy_bots/service.py`), using `load_benchmark_series` + `benchmark_return_fraction`
from `cadence.paper_trading.benchmark`. The AI paper-trading KPIs expose the same figures
to their detail page (`PaperTradingSessionKpisRead` → tiles in `PaperTradingSessionPage`),
so this change brings an established pattern to the bot detail page. The bot KPI read
(`BotKpis` → `BotKpisRead` → `GET /bots/sessions/{id}/kpis`) currently has no benchmark
fields; the detail page shows a `total_fees` tile that is always $0 for paper bots.

## Goals / Non-Goals

**Goals:**

- Surface benchmark return and excess return on the per-session bot KPI read, with the
  same availability semantics (absent without snapshots/closes) as the notification suffix.
- Replace the always-$0 fees tile with a single benchmark-comparison tile, 1-for-1, so the
  grid layout is unchanged.
- Keep the notification's benchmark line byte-identical by sharing one compute helper.

**Non-Goals:**

- No benchmark switcher on the bot detail page (unlike paper-trading); the header's static
  benchmark Fact stays.
- No absolute-dollar excess (`excess_return`); the tile is percentage-only, so only the two
  fractional figures + the benchmark id are added.
- No change to the value chart, dashboard adapter, snapshot/tick/sizing/trade-ledger, or the
  backend `total_fees` field (the notification still reads it).

## Decisions

**Share one benchmark-returns helper between the KPI and the notification.** Extract the
load + `benchmark_return_fraction` + excess computation into a private helper
(e.g. `_bot_benchmark_returns(session, bot, snapshots, *, total_return_pct, as_of) ->
tuple[float | None, float | None]` returning `(benchmark_return_pct, excess_return_pct)`).
`bot_session_kpis` calls it to populate the new KPI fields; `_bot_benchmark_suffix` calls it
and formats the existing string from the same tuple. This guarantees the tile and the daily
notification never diverge. _Alternative:_ duplicate the compute in `bot_session_kpis` —
rejected; two copies drift.

**KPI `as_of` is today.** `bot_session_kpis` is a live read, so it uses
`datetime.now(UTC).date()` as `as_of` (matching paper-trading's live KPI read), with
`start_date = snapshots[0].snapshot_date`. The notification keeps passing its snapshot-time
`as_of`, which the shared helper accepts as a parameter — so sharing the helper does not
change the notification's inputs.

**Add three fields, not four.** `BotKpis`/`BotKpisRead` gain `benchmark: str`,
`benchmark_return_pct: float | None`, `excess_return_pct: float | None`. The benchmark id is
included so the tile is self-contained; the display name is resolved client-side from the
existing `useBenchmarks` catalog (as paper-trading does), falling back to the id. `total_fees`
stays on the KPI (notification reads it) — only the frontend tile is removed. _Alternative:_
also add absolute `excess_return` like paper-trading — rejected as out of scope for a
percentage-only tile.

**Single combined tile, not two.** Paper-trading uses two tiles (Benchmark return + Excess
return). Here it is a 1-for-1 swap for the fees tile, so one tile carries the excess return as
the primary figure (coloured via `pnlClass`) and the benchmark return as the hint, headed
"vs {name}". When `benchmark_return_pct === null`, render an em-dash with a "needs a daily
snapshot" hint (mirrors the `TradeExtremeTile` null pattern already in the file).

## Risks / Trade-offs

- [Benchmark return and total return use slightly different bases — benchmark fraction is a
  per-dollar time-weighted buy-and-hold, total return is value-vs-allocated.] → This is the
  same basis paper-trading already ships and the notification already uses; excess is the
  documented, accepted comparison. No new semantics introduced.
- [Removing the fees tile hides fees from the detail page entirely.] → Fees are always $0 for
  paper bots (the motivation); the backend field and the daily notification still carry them,
  so nothing is lost operationally.
