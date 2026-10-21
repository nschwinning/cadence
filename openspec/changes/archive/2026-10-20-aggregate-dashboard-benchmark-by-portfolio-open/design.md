## Context

Two independent benchmark renderings exist today:

1. **Per-session** (session detail chart): `paper_trading/service.py::list_value_history` attaches a per-snapshot `benchmark_value` via `benchmark.py::rebased_benchmark_value(series, contributions, as_of)`, a contribution-aware dollar overlay rebased to the session's own capital and start date. This change does not touch it.
2. **Dashboard combined** (this change): `dashboard/service.py::_benchmark_overlays` ships each catalog index's raw daily closes; the client (`aggregate.ts::rebaseBenchmarkLine`) rebases a single index curve to `combinedSeries[0]` — the combined equity curve's first point.

The dashboard bug: at the combined curve's first date only the earliest-opened session holds capital, so the rebased benchmark reflects only that session's capital and never steps up as later sessions open. Meanwhile the equity line (`combinedSeries`) sums all selected sessions with carry-forward and steps up as each opens. The two are not comparable.

Key existing building blocks to reuse:
- `paper_trading/service.py::session_contributions(session_row, events, start_date)` — synthetic first contribution (build capital at start) + each capital-increase event, as `(effective_date, amount)`.
- `benchmark.py::BenchmarkSeries.close_on_or_before(when)` — bisect to the last close on/before a date (handles non-trading dates).
- The dashboard already does benchmark math on the client (`rebaseBenchmarkLine`), so client-side benchmark aggregation is the established pattern for this feature.

The chart's session-selection toggle recomputes the equity line **client-side** from already-fetched per-session data (no refetch). The benchmark must stay consistent with that: toggling a session off must drop its contribution from both lines, with no refetch.

## Goals / Non-Goals

**Goals:**
- Benchmark line per index = Σ over selected sessions of a buy-and-hold of each session's contributed capital in that index, bought at each contribution's effective date and held — stepping up as sessions open, contribution-aware.
- Preserve the per-index legend/toggle (default S&P 500, others opt-in) and no-refetch toggling for both session selection and benchmark selection.
- Keep the benchmark line summed over exactly the selected sessions so it tracks the equity line's selection.

**Non-Goals:**
- No change to the per-session detail chart, its benchmark overlay, or KPI benchmark/excess-return figures (the `service.py` "Do not unify them" note on the KPI fraction still holds).
- No new table, migration, benchmark catalog entry, or ingestion change.
- No change to which indexes exist or to the range windowing.

## Decisions

### Decision 1 — Where the per-session-summed aggregation happens: client-side, reusing shipped index closes plus per-session contributions (chosen)

The central question is how to keep the benchmark line summable over exactly the *selected* sessions (to match the equity line under the selection toggle) without a refetch per toggle.

**Chosen (Option C): ship raw index closes (unchanged) + add per-session contributions; aggregate on the client.**

The backend keeps shipping each index's raw closes (today's `DashboardBenchmarkSeries` shape, unchanged) and additionally returns, per session, that session's contributions `[{effective_date, amount}]` (from `session_contributions`). The client computes each selected index's line over the selected sessions.

The math reduces to a single units accumulator. For a date `t`:

```
benchmark(t) = close_on_or_before(index, t)
             × Σ over all contributions c of the SELECTED sessions with c.effective_date ≤ t
                 ( c.amount / close_on_or_before(index, c.effective_date) )
```

This is exactly `Σ_sessions rebased_benchmark_value(session, index, t)` — each contribution buys `amount / close(date)` units of the index at its date; the line is `close(t) × cumulative_units(t)`. It naturally yields zero before the first selected session opens and a step up on each session open and each capital increase, mirroring `combinedSeries`.

Rationale:
- **Payload**: index closes are shared across sessions and already shipped; contributions are a handful of `(date, amount)` per session. Payload ≈ `indexes × closes + sessions × contributions` — far smaller than shipping per-session-per-index dollar points.
- **Selection consistency with no refetch**: the client already re-aggregates the equity line from per-session data on toggle; it now re-aggregates the benchmark the same way, over the same selected set, for both the session toggle and the index toggle.
- **Smallest delta from today**: closes are already shipped and benchmark math already lives on the client; we add one field and change the aggregation function.

**Alternatives considered:**
- **Option D — backend returns per-session, per-index dollar overlays.** Keeps financial math on the backend but multiplies payload by `indexes × sessions × points` (e.g. 8 indexes × several sessions × up to ~250 daily points), for data the client must still re-sum per selection. Rejected on payload for no behavioral gain.
- **Option B — backend returns one all-sessions aggregate per index.** Smallest payload but it cannot react to the session-selection toggle without a refetch, so the benchmark line would stay fixed while the equity line drops when a session is excluded — the exact inconsistency we are fixing. Rejected.

### Decision 2 — Contribution date vs. index close alignment

A contribution's `effective_date` may fall on a non-trading day or before the earliest stored close for an index. Use `close_on_or_before` for both the valuation date and each contribution date. A contribution whose effective date precedes all stored closes for an index contributes zero units for that index (no error) — consistent with the "benchmark with no data draws no line / inert" handling. This is ported to the client as a small pure helper mirroring `BenchmarkSeries.close_on_or_before` (bisect on ascending closes).

### Decision 3 — Date axis and carry-forward

The benchmark line is evaluated on the same common date axis as `combinedSeries` (the union of selected sessions' value dates, windowed to the range). Because the benchmark value at any date is a closed-form function of the index close on/before that date and the cumulative units, no carry-forward special-casing is needed — but the axis is shared so equity and benchmark align point-for-point for the tooltip.

### Decision 4 — Schema shape

Add `contributions: [{ effective_date: date, amount: float }]` to `DashboardSessionPerformance` (backend `api/schemas.py` and frontend `types/api.ts`). `DashboardBenchmarkSeries` stays raw `{date, price}` closes. `rebaseBenchmarkLine` in `aggregate.ts` is replaced by a per-session contribution-aware aggregator (`benchmarkDollarSeries(selectedSessions, indexClosesById, selectedBenchmarkIds, dateAxis)` or equivalent), unit-tested in isolation.

## Risks / Trade-offs

- **Financial math on the client.** Porting the units/`close_on_or_before` logic to TS duplicates a slice of `benchmark.py`. Mitigation: the dashboard already rebases on the client; keep the new helper pure and cover it with unit tests that mirror the backend's expectations (two sessions opened on different dates sum and step up; capital-increase step-up; missing-history → zero).
- **Contributions correctness.** The dashboard must derive contributions exactly as the session detail does (`session_contributions`), including the synthetic opening contribution, so the benchmark's opening capital matches each session's actual deployed capital. Mitigation: reuse `session_contributions` on the backend rather than re-deriving from allocated_capital alone.
- **Payload growth from contributions.** Negligible — a few `(date, amount)` entries per session.
- **Windowing of contributions before the range start.** For a sub-Max range, a session's opening contribution may predate the range window. The units accumulator still values correctly within the window (units bought earlier are already held); the line is simply clipped to the range axis like the equity line. Covered by a test.
