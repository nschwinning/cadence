## Context

The Dashboard's point-in-time value band (`ValueTiles` in `pages/dashboard/HeroTiles.tsx`) currently renders a single `StatTile` ("Total value") inside a `lg:grid-cols-4` grid, so it sits at a quarter width and the band looks empty. We are adding three more point-in-time figures. Two of them (total return %, lifetime P&L $) are pure client aggregations of data the overview already returns (`current_value` + `contributions`). The third (return vs benchmark) needs the backend to serve one new per-session number so the client can aggregate an excess figure over whatever sessions are selected — selection is client-side and must not trigger a refetch.

## Goals / Non-Goals

**Goals**
- Four live/point-in-time tiles in the value band, spanning full width, all range-independent.
- Reuse existing backend buy-and-hold machinery; no new return math, no migration, no new endpoint.
- Preserve client-side re-aggregation on selection toggle with no refetch.

**Non-Goals**
- No change to the range-scoped performance tiles, the combined equity chart/overlay, leaderboard, universe, automation, recent activity.
- No change to the 30s live refresh cadence.
- No change to the session-detail KPIs or its TWR chart.

## Decisions

### Benchmark basis: money-weighted (contribution-aware), not the session-detail KPI

There are two distinct benchmark computations in `paper_trading/benchmark.py`:

- `benchmark_return_fraction(series, start_date, as_of)` — a **time-weighted, per-dollar** buy-and-hold return (`close(as_of)/close(start) − 1`). The **session-detail** excess KPI (`paper_trading/service.py` `session_kpis`) uses this, and a code comment there explicitly warns against unifying the two bases.
- `rebased_benchmark_value(series, contributions, as_of)` — a **contribution-aware dollar** buy-and-hold: each contribution buys units at its effective-date close and is held, valued at `as_of`. The **dashboard's combined-equity benchmark overlay** uses this basis.

The new dashboard value-band figures compute portfolio total return as a **money-weighted** simple return `(Σ current_value − Σ contributed) ÷ Σ contributed`. For the benchmark leg to be a like-for-like comparison, it must also be money-weighted, i.e. contribution-aware. **Decision:** `benchmark_value` uses `rebased_benchmark_value` (the dashboard overlay basis), NOT `benchmark_return_fraction` (the session-detail KPI basis). The aggregate benchmark return is then `(Σ benchmark_value − Σ contributed) ÷ Σ contributed`, and excess = portfolio return − benchmark return. This keeps both legs money-weighted and internally consistent, and reuses the exact function the overlay already uses.

Consequence: the dashboard's aggregate excess will not numerically equal the session-detail per-session excess KPI (which is time-weighted). This is intentional and correct for an aggregate money-weighted view; the session-detail page is untouched.

### `benchmark_value` is since-inception / range-independent

`_session_performance` already builds a range-windowed `points` series but derives `contributions` from the session's **first** snapshot date (not range-windowed). `benchmark_value` is likewise since-inception: load the full benchmark series (`load_benchmark_series`, no range floor) and value the contributions at the latest available close. `as_of` is the latest benchmark close date available for the session's benchmark (via `close_on_or_before`), consistent with how the overlay values its latest point; concretely we pass `as_of = today` (ET date already used elsewhere in the service) and rely on `close_on_or_before` to degrade to the last stored close. Null when `rebased_benchmark_value` returns `None` (no priceable close for any contribution) or the session has no contributions yet.

### Null/unavailable propagation (vs-benchmark tile)

If **any** selected session has `benchmark_value === null`, the aggregate excess is not computed and the tile shows a "not yet available" state. Rationale: silently dropping a session from the benchmark leg while keeping it in the portfolio leg would report a misleading excess (comparing a portfolio total against a benchmark total covering fewer sessions). This is the simplest honest behaviour. (Alternative considered: exclude unpriceable sessions from both legs of the excess only — rejected as more surprising and harder to explain in a single tile.)

### Total return / lifetime P&L basis

Money-weighted simple since-inception return against total contributed capital, consistent with how contributions already drive the overlay. When `Σ contributed <= 0` (no contributions yet, e.g. a session with no snapshots), total return % is shown as a neutral placeholder (em dash) rather than dividing by zero; lifetime P&L is still `Σ current_value − Σ contributed` (which is `Σ current_value` when contributed is 0).

### Layout

The value band grid becomes a full-width 4-up: `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4`, four `StatTile`s. Reuse the existing `StatTile` + `signClass(value)`. Keep the live `FreshnessBadge` on the band and the "N selected portfolios · point-in-time" hint.

## Data flow

Backend `_session_performance` → `SessionPerformance.benchmark_value: float | None` → `DashboardSessionPerformance.benchmark_value` (Pydantic) → `types/api.ts` → `aggregate.ts` helpers → `ValueTiles`. No new query: `_session_performance` already loads `history` and `contributions`; it adds one `load_benchmark_series(session, session_row.benchmark)` + `rebased_benchmark_value(...)` call (the benchmark series load mirrors what `_benchmark_overlays`/`session_kpis` already do).

## Risks / Trade-offs

- **Extra benchmark-series load per session** in `_session_performance`. Mirrors the cost already paid by `session_kpis`/the overlay; acceptable for the handful of active sessions on the dashboard. If it ever matters, the series per `benchmark` value could be memoised within one overview build — not done now (premature).
- **Two benchmark bases coexist** (time-weighted KPI vs money-weighted dashboard). Documented above and in code comments at the call site to prevent a future "unify" refactor.

## Migration Plan

None. No schema change, no new endpoint, additive nullable field only. Frontend and backend ship together; an older frontend simply ignores the new field, and the new frontend treats a missing/null `benchmark_value` as "not yet available".

## Open Questions

None outstanding; the benchmark-basis and null-propagation decisions above resolve the only material ambiguities.
