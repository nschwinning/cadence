## Context

`get_dashboard_overview` (`backend/src/cadence/dashboard/service.py`) builds per-session `SessionPerformance` and a set of benchmark overlay price series. The benchmark lines are drawn **client-side**: `frontend/src/pages/dashboard/aggregate.ts::benchmarkDollarSeries` treats each session contribution as buying `amount / closeOnOrBefore(points, effective_date)` index units, held forward, and sums across the selected sessions over the combined date axis.

Two dates drive this today:

- **Session value points** are windowed to the range start: `points = [p for p in history if start_date is None or p.date >= start_date]`.
- **Contributions are not windowed**: the opening contribution uses `history[0].snapshot.snapshot_date` (the session's true first snapshot), plus any capital increases.

The benchmark overlay floor is `overlay_floor = min(session_point_dates)` — the earliest **windowed** value point — and `_benchmark_overlays` keeps closes on/after that floor plus a single pre-floor close as a rebasing anchor. When a session opened before `start_date`, its windowed first point is `>= start_date`, so `overlay_floor` can sit after that session's contribution date. The anchor (last close strictly before the floor) is then still after the contribution date, so `closeOnOrBefore` returns `null`, the contribution buys zero units, and the session drops out of the benchmark line. Verified live: 1M range, floor 2026-09-21, anchor 2026-09-18, a session's contribution at 2026-09-16 → dropped → benchmark ≈ $20k for three $10k portfolios.

## Goals / Non-Goals

**Goals:**
- Every active session's contribution is priceable by the client, so none is dropped from the benchmark line, for every range.
- No visible change to the plotted benchmark era (the line still spans the windowed combined axis), and an exact no-op for the `Max` range.

**Non-Goals:**
- Windowing the contributions, or otherwise changing how contributions are derived.
- Any change to the combined-equity actual line, the per-index legend / default-S&P-500 / rebase-free design, schema, migration, endpoints, or `benchmark_prices` ingestion.
- Any frontend change: `aggregate.ts` is already correct and only needs priceable points.

## Decisions

**Extend the overlay floor to cover the earliest contribution.** In `get_dashboard_overview`, fold the sessions' contribution effective-dates into the floor:

```python
contribution_dates = [c.effective_date for perf in sessions for c in perf.contributions]
overlay_floor = min([*session_point_dates, *contribution_dates], default=None)
```

Because every session's opening contribution date (`history[0]` snapshot date) is `<=` that session's earliest windowed value point, the new floor is `<=` the old floor and `<=` the earliest contribution across sessions. `_benchmark_overlays` then prepends the last close strictly before that floor as its anchor, so `closeOnOrBefore(points, c.effective_date)` resolves for every contribution. `_benchmark_overlays` itself is unchanged; only the `floor` it receives changes. Its docstring is updated to say the window also covers the earliest contribution so every contribution is priceable.

**Why the plotted era does not grow.** `benchmarkDollarSeries` maps only over `dateAxis` (the windowed combined equity axis). The additional pre-range closes are consulted solely by `closeOnOrBefore` for unit counts; they add no plotted points. So the benchmark line still visually starts where the combined equity line does.

**Alternative considered — window the contributions to the range.** Rejected: contributions before the range are still *held* within it; dropping them would misstate the buy-and-hold just as badly, only in the opposite direction, and would contradict the archived `aggregate-dashboard-benchmark-by-portfolio-open` design.

## Risks / Trade-offs

- **Slightly more index history shipped** when a session opened well before the range start — bounded by the earliest active session's opening date (not "decades"), and only prices (date, close) pairs. Acceptable.
- **No-op risk for `Max`:** for `Max`, `start_date is None`, so value points are already unwindowed and `min(session_point_dates)` already sits at/before the earliest contribution; folding contribution dates in cannot move the floor later, and in practice leaves it unchanged. A regression test pins this.
