# Tasks

## 1. Backend — constants & profile definition

- [x] 1.1 Add `WATCHLIST_MIN_BARS` (default 40) to `technical_indicators/constants.py` with a comment on the rationale (MACD slow 26 + signal 9 ≈ 34, margin to 40).
- [x] 1.2 Define the short-window profile in one place (constants/service): the set of indicator keys surfaced for watchlist (RSI14, MACD line/signal/hist, EMA20, Bollinger %b + bandwidth, 20-day historical volatility, volume ratio vs 50-day avg, OBV 20-day change) and the short-window reversal flags; and the long-window/trend-gate keys excluded from the watchlist signal.

## 2. Backend — storage seam (Option A, decided — see design D3)

- [x] 2.1 Add a nullable `bar_count` column to the snapshot model in `technical_indicators/models.py`.
- [x] 2.2 Create the Alembic migration (additive, nullable; no backfill — the nightly run repopulates). Verify round-trip up/down.

## 3. Backend — nightly job covers watchlist

- [x] 3.1 Extend `technical_indicators/service.py::execute_run` (and its asset-selection query) to also iterate `membership = watchlist` assets alongside the universe, reusing `compute_and_store`, per-asset commit, and the run audit (processed/failed counts include watchlist).
- [x] 3.2 In the compute/store path, record the daily-bar count on the snapshot so below-floor watchlist assets are represented as insufficient-history (`bar_count < WATCHLIST_MIN_BARS`), not mostly-null snapshots.

## 4. Backend — read path & schema

- [x] 4.1 Add the watchlist short-window read projection (preferred: a dedicated `WatchlistIndicatorsRead` schema in `api/schemas.py`) exposing the short-window subset + an `insufficient_history` flag, and NOT presenting the long-window indicators / trend-gate verdict as a signal.
- [x] 4.2 Embed the watchlist technical indicators in the watchlist asset read payload (preferred, avoids N requests) OR expose a per-ticker read; wire the service read to derive insufficient-history from `bar_count < WATCHLIST_MIN_BARS`.
- [x] 4.3 Confirm no universe/trading read path changed (do NOT touch `list_assets` trading defaults, `flows/build.py`, `flows/rebalance.py`).

## 5. Backend — tests

- [x] 5.1 Unit test: watchlist asset at/above `WATCHLIST_MIN_BARS` → short-window values present, no insufficient-history marker.
- [x] 5.2 Unit test: watchlist asset below the floor → insufficient-history marker, not a mostly-null snapshot.
- [x] 5.3 Unit test: `execute_run` now processes watchlist assets (coverage + run-audit counts include them).
- [x] 5.4 Unit test: the watchlist read projection omits the long-window indicators / trend-gate verdict as a signal and exposes only the short-window subset.
- [x] 5.5 Test: a universe asset's snapshot/read behavior is unchanged (regression guard).

## 6. Frontend — Watchlist technical panel

- [x] 6.1 Extend `types/api.ts` with the watchlist technical-indicator shape (short-window fields + `insufficient_history`).
- [x] 6.2 Add a `TechnicalPanel` (or section) in `pages/watchlist/WatchlistPage.tsx` per entry rendering the short-window profile, mirroring the `FundamentalsPanel` pattern.
- [x] 6.3 Render an explicit "insufficient history (needs ≥ N bars)" state when the entry is below the floor.
- [x] 6.4 Wire the data (embedded in the watchlist read payload per 4.2, or a small indicators client call).

## 7. Frontend — tests

- [x] 7.1 Vitest: the Watchlist technical panel renders the short-window indicators for an entry with sufficient history.
- [x] 7.2 Vitest: the Watchlist panel shows the insufficient-history state for a below-floor entry.

## 8. Verification gates

- [x] 8.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 8.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 8.3 `openspec validate add-watchlist-short-window-indicators --strict` passes.
