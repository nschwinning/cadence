## Why

The dashboard combined-equity chart draws a benchmark line that **undercounts** the benchmark whenever a selected portfolio opened **before the current range's start**. Verified against live data: three active portfolios each opened with $10,000 (on 2026-09-16, 2026-09-28, and 2026-10-08), yet at the default 1M range the benchmark line sits near **$20,000** instead of ~$30,000 — one portfolio's capital is silently missing from the benchmark.

Root cause: the overview's benchmark price series is windowed to the earliest **range-windowed** session value-point (with only a single pre-floor close kept as a rebasing anchor), but each session's benchmark **contribution** is **not** windowed — the opening contribution carries the session's true first-snapshot date. When a session opened before the range start, its contribution's effective date precedes the floored anchor, so the client's `closeOnOrBefore` lookup returns nothing, that contribution buys zero index units, and it is dropped from the benchmark line. The combined-equity (actual) line is unaffected, so the two lines disagree by exactly the dropped portfolio's capital.

## What Changes

- The overview's benchmark price series will reach back far enough to price the **earliest contribution across the active sessions**, not merely the earliest range-windowed value point. Concretely, the price-series floor becomes the minimum of the windowed session value-point dates **and** every session's contribution effective dates, so the series' pre-floor anchor precedes every contribution and every contribution is priceable.
- As a result, a portfolio that opened before the range start is counted in the benchmark line again, and the benchmark steps up as each selected session opens — matching the combined-equity aggregation.
- No change to how contributions are derived (they stay non-windowed), to the combined-equity actual line, to the per-index legend / default-S&P-500 / rebase-free design, or to any schema, migration, or endpoint. The extra early index closes are consulted only for unit pricing; the plotted benchmark line still spans only the windowed combined date axis, so there is no visible pre-range line. The change is a no-op for the `Max` range, where the floor already covers each session's opening.

## Capabilities

### Modified Capabilities
- `dashboard`: The "Benchmark price series in the overview" requirement is tightened so the per-index price series' date window covers the earliest session contribution (not just the earliest range-windowed value point), guaranteeing every selected session's contribution is priceable and none is dropped from the benchmark line.

## Impact

- Backend only: `backend/src/cadence/dashboard/service.py` — the `overlay_floor` computation in `get_dashboard_overview` (and the `_benchmark_overlays` docstring describing the window).
- No frontend change: the client aggregator (`frontend/src/pages/dashboard/aggregate.ts`) is already correct; it only needs the backend to supply priceable points.
- No schema, migration, API shape, or benchmark-ingestion change.
