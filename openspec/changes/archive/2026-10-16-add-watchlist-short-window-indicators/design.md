## Context

Technical indicators are computed nightly by a single-worker runner
(`technical_indicators/service.py::execute_run`) that iterates the **universe**
only and upserts one snapshot row per asset via `compute_and_store`. The compute
engine (`compute.py::compute_snapshot`) is ticker-agnostic, close+volume-only,
and already degrades gracefully: insufficient history yields `None` per indicator
(never an error), empty bars yield a `None` snapshot. History is fetched with
yfinance `period="max"`.

Watchlist assets (Asset.membership == WATCHLIST) are emerging names that must be
Alpaca-tradable but are exempt from the universe maturity bar (stocks ≥ 5y,
crypto ≥ 1y), so they typically have well under a year of history — below the
~220 bars the SMA200-slope trend gate needs. They currently get no snapshot and
never enter trading (trading reads `list_assets`, default `membership=universe`).

This change computes a short-window profile for watchlist assets and shows it on
the Watchlist page. Trading is untouched.

## Goals / Non-Goals

**Goals**
- Compute + store indicator snapshots for watchlist assets via the existing job.
- Surface a short-window subset (RSI, MACD, EMA20, Bollinger, hist-vol, volume
  ratio, OBV change, short-window reversal flags) as the meaningful watchlist
  profile; keep the long-window set and the trend-gate verdict out of the
  watchlist trading narrative.
- Apply a tunable minimum-history floor; mark below-floor assets
  "insufficient history" instead of emitting mostly-null values.
- Render the profile (and the insufficient-history state) per entry on the
  Watchlist page.

**Non-Goals**
- No trading of watchlist assets; no change to `flows/build.py`,
  `flows/rebalance.py`, `list_assets` trading defaults, `use_technical_indicators`,
  or the universe trend gate.
- No new indicators; no new crypto-specific handling.

## Decisions

### D1 — Extend the existing nightly job rather than add a second job
Add watchlist membership to the asset set `execute_run` iterates (alongside the
universe). Reuse `compute_and_store`, the per-asset commit, and the run audit so
watchlist assets flow through the same single-worker, fault-isolated path. One job,
one audit — simplest and consistent with the current architecture.

### D2 — Minimum-history floor as a tunable constant, default ~40 bars
Add `WATCHLIST_MIN_BARS` (proposed default **40**) to
`technical_indicators/constants.py`. Rationale: the longest short-window input is
MACD (slow EMA 26 + 9-period signal ≈ 34 bars); 40 gives a clean margin. Below the
floor, record an insufficient-history marker; at/above it, store the short-window
values. The floor applies to watchlist assets only — universe behavior is
unchanged. The value is a tunable assumption, easily adjusted later.

### D3 — Storage seam for the insufficient-history marker (DECIDED: Option A)
The snapshot model stores computed values + trading date. The floor needs a
distinguishable "insufficient history" state. **Decision: persist a small marker
on the snapshot row.** Add a nullable `bar_count` column (and derive
insufficient-history as `bar_count < WATCHLIST_MIN_BARS`) to the snapshot model
plus one additive, nullable Alembic migration. `compute_and_store` records the
daily-bar count; the watchlist read derives the insufficient-history flag from it.
This is unambiguous, queryable, survives restarts, and matches the project's
"service owns state" convention — unlike representing below-floor as "no snapshot
stored," which would conflate "never computed" with "below floor" and could leave
a stale row after a universe↔watchlist membership flip.

### D4 — Short-window subset is a read/display concern, not a compute change
`compute_snapshot` still produces the full snapshot (it is ticker-agnostic and
cheap). The short-window *selection* is applied where watchlist indicators are
read/serialized: the read path returns the short-window fields for watchlist
assets and omits/flags the long-window + trend-gate fields as non-signals. This
avoids forking the compute engine. The exact projection (a dedicated read schema
vs. reusing the existing one with the long-window fields suppressed for watchlist)
is decided in the read-schema task; a dedicated `WatchlistIndicatorsRead` is
cleanest.

### D5 — Frontend: a per-entry technical panel on the Watchlist page
Mirror the existing `FundamentalsPanel` pattern: a `TechnicalPanel` (or section)
per watchlist entry rendering the short-window profile, with an explicit
"insufficient history (needs ≥ N bars)" state. Fetch via the watchlist read (either
the indicators are embedded in the watchlist asset read, or a small
technical-indicators client call keyed per ticker — decided in the read-schema
task; embedding in the watchlist payload avoids N requests and is preferred).

## Risks / Trade-offs

- **Stale watchlist snapshots** until the next nightly run after an asset is added
  — acceptable; matches universe behavior (also computed nightly). A watchlist
  asset added mid-day simply shows "no technical data yet" until the next run.
- **Floor tuning**: 40 is a heuristic. If too strict, recent-but-viable IPOs show
  insufficient-history; if too loose, MACD/Bollinger are noisy. Tunable constant.
- **Option A migration** touches the shared snapshot table; keep the new column
  nullable with a safe default so universe rows are unaffected.

## Migration Plan

If Option A: one additive, nullable column (+ default) via Alembic; no backfill
required (nightly run repopulates). No data migration for universe rows.

## Open Questions

- Exact default for `WATCHLIST_MIN_BARS` — resolved at apply time to **40**.

## Resolved during apply

- **Read seam: a dedicated batched endpoint, not embedding in `AssetRead`.**
  `GET /api/v1/technical-indicators/watchlist` returns the short-window profile
  for all watchlist assets in one call (with the `min_bars` floor and a per-asset
  `insufficient_history` flag). This keeps the `assets` module fully decoupled
  from `technical_indicators` (consistent with trading reading TI through its own
  service), still avoids N+1, and satisfies both specs ("a read of a watchlist
  asset's indicators"). The frontend makes one extra batched query alongside
  `useWatchlist()` and merges by `asset_id`.
- **The nightly runner already iterates watchlist assets.**
  `execute_run` selects `Asset` unfiltered (no membership filter), so watchlist
  assets already receive snapshots and are counted in the run audit. Task 3.1 is
  therefore a verification + regression test, not a change to the iteration; the
  only compute-path change is recording `bar_count`.
