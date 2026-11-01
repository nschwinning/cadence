# Tasks

## 1. Last-official-close lookup

- [x] 1.1 Decide the close source (per design Open Questions): confirm whether
  `price_history` stores daily closes for **held** tickers, not only benchmarks. If
  yes, read the latest stored close on/before the valuation day; otherwise fall back
  to a bounded `MarketDataProvider.fetch_daily_closes` over a short trailing window
  (enough to span a long holiday weekend).
- [x] 1.2 Add a helper in `paper_trading/service.py` that, given the session's equity
  tickers and the valuation day, returns a `{ticker: last_close}` map, batched, with
  absent tickers simply omitted (degrade-friendly, never raising).
- [x] 1.3 Unit-test the helper: returns the most recent close on/before the day
  (prior trading day for a weekend/holiday), omits tickers with no close, and handles
  an empty ticker list.

## 2. Market-closed marking in `compute_session_value`

- [x] 2.1 Query the broker's `is_market_open()` once per `compute_session_value`
  call and thread the result into per-position marking.
- [x] 2.2 When the market is **closed**, mark open **equity** positions to their last
  official close (from the task-1 helper); keep **crypto** positions marked live via
  `quote_price`. When the market is **open**, keep the existing live-quote marking for
  all positions.
- [x] 2.3 Preserve the degradation chain: for a closed-market equity, fall back to a
  live quote if no close is available, then to `avg_cost`; never fail the valuation.
  Classify crypto vs equity via the existing asset `category` discriminator (missing
  category → treated as equity).
- [x] 2.4 Unit-test `compute_session_value`: market-closed marks equities at the last
  close and crypto live; market-open is unchanged; close-unavailable falls back to
  quote then avg cost; a stocks-only session yields the same value across a
  non-trading day (no drift).

## 3. Weekend snapshot gate on actual crypto holdings

- [x] 3.1 In the end-of-day selection (`ai_portfolio/snapshots.py` /
  `snapshot_all_sessions`), replace the weekend `session_allows_crypto(...)` scope
  test with a **holds-crypto** test over the session's open position ledger (include
  on a weekend iff it currently holds ≥1 crypto position). Leave weekday selection and
  the weekend crypto *rebalance* selection unchanged; keep `session_allows_crypto` for
  the rebalance path.
- [x] 3.2 Unit-test weekend selection: a session holding crypto is snapshotted on a
  weekend; a session configured `both`/no-scope but holding no crypto is skipped
  (no snapshot, no notification); weekday behavior unchanged; confirm the daily-run
  assembly (which defers to this selection) tracks the new gate.

## 4. Cross-path verification

- [x] 4.1 Add/extend a test asserting the live KPI summary (`session_kpis`) and the
  P&L triple (`session_pnl_triple`) report the frozen (last-close) equity value while
  the market is closed, confirming the single-chokepoint fix reaches the live read
  paths and the UI-facing output (no separate read-path patch needed).

## 5. Verify gates

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green.
- [x] 5.2 `openspec validate fix-market-closed-valuation --strict` — valid.
