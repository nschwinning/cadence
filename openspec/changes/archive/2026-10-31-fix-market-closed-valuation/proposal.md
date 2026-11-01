## Why

A user observed stocks-only paper-trading portfolios reporting a day's profit/loss
on a **Saturday**, when the equity market is closed and those sessions hold nothing
that trades on weekends. That is wrong, and it has two independent root causes:

1. **Live marking drifts while the market is closed.** The single valuation
   chokepoint — `compute_session_value` (used by the end-of-day snapshot, the live
   KPI summary, the session P&L/return reads, and rebalance sizing) — always marks
   open equity positions to the **live latest quote** (the NBBO quote midpoint). On
   a weekend or after hours that "latest quote" is not the official close and can
   still move (stale-quote updates, pre/post-market prints), so a stocks-only
   session's valuation wanders even though nothing has actually traded. Every live
   read path re-marks on each request, so the UI tiles drift too.

2. **The weekend snapshot skip keys off configured scope, not holdings.** The
   end-of-day job skips stocks-only sessions on weekends only by **configured asset
   scope**, and a session with no persisted scope defaults to `both` — so a session
   that is de-facto stocks-only (scope `both` but holding no crypto) is still
   snapshotted and pushed on a weekend, producing the spurious Saturday P&L line.

The fix is to value positions against the **last official close when the market is
closed** at the shared chokepoint (making weekend/holiday valuations stable across
every read path at the source), and to gate the weekend snapshot on a session's
**actual crypto holdings** rather than its configured scope.

## What Changes

- **Value equities at the last official close when the equity market is closed.**
  `compute_session_value` (the one function behind the snapshot, the live KPI
  summary, the P&L/return reads, rebalance sizing, and the daily-run learning
  snapshot) SHALL, when the broker reports the equity market closed, mark open
  **equity** positions to their **last official daily close** instead of a live
  quote. Crypto positions SHALL always be valued live (crypto trades 24/7). When
  the market is open, equities continue to be valued at live quotes exactly as
  today. If a close cannot be obtained, valuation falls back to the existing
  behavior (a live quote if available, else the position's average cost) rather than
  failing. This freezes weekend/after-hours valuations at the source, so Saturday's
  equity value equals Friday's close across the snapshot, the KPIs, the P&L triple,
  and the UI tiles — killing the drift in one place (covers fix directions #1 and
  #3, which share this chokepoint).
- **Gate the weekend snapshot on actual crypto holdings.** The end-of-day
  snapshot/P&L job SHALL, on a weekend, select only sessions that **currently hold
  at least one crypto position**, rather than selecting by configured asset scope
  (and no longer treats a missing scope as `both` for this purpose). A session
  holding no crypto is skipped entirely on a weekend — no snapshot, no
  notification — so a de-facto stocks-only session no longer produces a weekend P&L
  line (fix direction #2). The daily-run learning assembly already defers to this
  same selection, so it tracks the new behavior with no separate change.

## Capabilities

### Modified Capabilities

- `ai-paper-trading`: Session valuation SHALL mark open equity positions to the
  last official close whenever the equity market is closed (crypto always live),
  uniformly across the end-of-day snapshot, the live KPI summary, the P&L/return
  reads, rebalance sizing, and the daily-run learning snapshot; and the weekend
  end-of-day snapshot SHALL select sessions by their actual crypto holdings rather
  than by configured asset scope.

## Impact

- **Backend — modified**: `paper_trading/service.py` — `compute_session_value`
  (and its `quote_price`/marking helpers) gains market-closed awareness via the
  broker's `is_market_open()` and a "last official close" lookup for equities;
  `ai_portfolio/snapshots.py` / the end-of-day selection
  (`session_allows_crypto` usage in `snapshot_all_sessions`) switches the weekend
  gate to actual crypto holdings. The "last official close" source reuses the
  existing daily-close seam (`MarketDataProvider.fetch_daily_closes` / stored
  `price_history` closes — chosen in design).
- **No migration, no schema/model change, no config change.** The snapshot cron
  still runs every calendar day; weekend behavior is now driven by holdings +
  market-closed marking, not by the schedule.
- **No frontend change.** The dashboard/session KPI tiles render backend valuation
  output, so freezing the backend chokepoint freezes the tiles; no client code
  computes live value independently.

## Out of Scope

- The **weekend crypto rebalance** selection ("Weekend crypto rebalance selects
  sessions by configured crypto scope") is a separate feature about *when crypto
  trades*, not about valuation; it is deliberately left unchanged.
- No change to **when** the snapshot/P&L cron runs (deployment concern), to the
  benchmark ingestion schedule, or to how crypto is priced (always live).
- No change to realised-P&L, fees, contributed-capital, or time-weighted-return
  accounting — only the price used to mark **open equity positions while the market
  is closed** changes.

## Assumptions (for review)

1. **Weekend selection is holdings-based, scope-independent.** On a weekend the
   snapshot includes a session iff it currently holds ≥1 crypto position, for any
   configured scope. A crypto-allowed session that is momentarily flat on crypto is
   therefore skipped on that weekend day (its value does not move) — acceptable,
   since it has nothing weekend-tradable. (Narrowable at review, e.g. to "scope
   includes crypto AND holds crypto.")
2. **"Last official close" = the most recent completed daily close** on or before
   the valuation day, from the project's existing daily-close source. For a
   Saturday/Sunday or a market holiday this is the prior trading day's close
   (e.g. Friday). The exact source (freshly fetched vs stored `price_history`) is
   chosen in design; both resolve to the same official close.
3. **Market-open/closed is determined by the broker clock** (`is_market_open()`),
   which already governs weekend/holiday equity trading, so valuation and trading
   agree on when the market is closed.
