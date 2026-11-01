## Context

A stocks-only session showed a day's P&L on a Saturday. Tracing it surfaced two
independent defects, both in the AI paper-trading valuation path:

1. **`compute_session_value`** (`paper_trading/service.py`) marks open equity
   positions to the **live latest quote** on every call — `quote_price(...)` reads
   `Quote.mid` (the NBBO bid/ask midpoint), falling back to `ask`, then to the
   position's `avg_cost`. There is no awareness of whether the market is open, so on
   a weekend/after-hours the "latest quote" is not the official close and still
   drifts. This one function is the chokepoint behind the end-of-day snapshot
   (`record_value_snapshot`), the live KPI summary (`session_kpis`), the P&L triple
   (`session_pnl_triple`), and rebalance sizing (current marked-to-market value).
   Every live read re-marks on each request, so the UI tiles drift too.

2. The end-of-day job's **weekend skip** keys off *configured scope*
   (`session_allows_crypto` → `metadata["asset_types"]`, defaulting to `both` when
   absent), not actual holdings. A session with scope `both` (or no persisted scope)
   that holds only stocks is therefore snapshotted and pushed on a weekend.

The guiding decision: **fix the valuation at the one shared chokepoint** (so the
snapshot, KPIs, triple, and tiles all freeze consistently when the market is closed —
fix directions #1 and #3 collapse into one change), and **gate the weekend snapshot
on actual crypto holdings** (fix direction #2).

## Goals / Non-Goals

**Goals**
- When the equity market is closed, mark open **equity** positions to the **last
  official daily close** instead of a live quote, at `compute_session_value`, so all
  downstream read paths inherit it. Crypto stays live.
- Make weekend snapshot selection depend on a session's **actual crypto holdings**.
- Graceful degradation: a missing close falls back to the current behavior (live
  quote, then avg cost); never fail a valuation because a close is unavailable.
- No migration, no schema/model change, no config change, no frontend change.

**Non-Goals**
- No change to the **weekend crypto rebalance** selection (a trading-cadence
  feature, not a valuation one) — explicitly left on configured scope.
- No change to realised-P&L, fees, contributed capital, or time-weighted-return math.
- No change to crypto pricing (always live), benchmark ingestion, or the cron
  schedules.

## Decisions

### Market-closed awareness at the single chokepoint

`compute_session_value` learns whether the equity market is open from the broker's
`is_market_open()` (already present on the `Broker` protocol, `broker/base.py:131`;
implemented by Alpaca's clock and by `StubBroker`). It is queried **once per
valuation call** and threaded into the per-position marking so equities and crypto
are priced differently:

- **Market open** → unchanged: equities and crypto both marked via `quote_price`
  (live quote).
- **Market closed** → equities marked at their **last official daily close**; crypto
  marked live via `quote_price` (crypto is 24/7, so its live price is correct on a
  weekend).

Asset class is already known at this seam (the position ledger / asset rows carry
`category`), the same discriminator the executor uses to size crypto fractionally vs
equities whole-share. Crypto detection reuses that existing classification; no new
flag.

Because this is the only function that marks positions for the snapshot, KPIs, P&L
triple, and rebalance sizing, fixing it here is sufficient — no read path is patched
individually. The spec states the rule once (a cross-cutting ADDED requirement) and
notes it governs each of those paths.

### "Last official close" source

Two existing sources can supply the official close; both resolve to the same figure:

1. **`MarketDataProvider.fetch_daily_closes(tickers, start, end)`**
   (`assets/market_data.py:115`) — the canonical daily-close seam, already used by
   price-history/benchmark ingestion. Batch, ascending `(date, close)` per ticker, a
   ticker absent from the map when unavailable (degrade-friendly). The last point on
   or before the valuation day is the official close.
2. **Stored `price_history` closes** (`price_history/service.py`) — if the project
   already ingests per-asset daily closes, reading the latest stored close avoids a
   network call inside a valuation request.

**Recommendation:** prefer the stored-closes path when the held tickers' closes are
already ingested (no network I/O in a read request), and fall back to a bounded
`fetch_daily_closes` over a short trailing window (e.g. ~7 calendar days, enough to
span a long holiday weekend) for any ticker without a stored close. Finalized in
apply once it is confirmed whether `price_history` stores closes for all **held**
tickers (not only benchmarks). Either way the lookup is batched over the session's
equity tickers, and any ticker that yields no close falls through to the existing
fallback chain.

*(Open question recorded below: stored-vs-fetched primary source.)*

### Degradation contract (unchanged shape)

`quote_price`'s existing fallback order is preserved. The market-closed branch adds a
**preceding** step for equities only: try last official close → (if none) live quote
→ (if none) `avg_cost`. Crypto and the market-open path are untouched, so a broker
clock/outage never makes valuation worse than today; at worst it behaves exactly as
the current code.

### Weekend snapshot gate on actual holdings

In the end-of-day selection (`ai_portfolio/snapshots.py` / `snapshot_all_sessions`),
the weekend branch replaces the `session_allows_crypto(session_row)` scope test with
a **holds-crypto** test over the session's open position ledger: include the session
on a weekend iff it currently holds ≥1 crypto position. This removes the
`metadata["asset_types"]`-defaults-to-`both` bypass for weekend selection.

- Weekday selection is unchanged (all active AI sessions).
- The **daily-run learning assembly** already selects "the same sessions as the P&L
  job" (spec "Scheduled assembly of daily-run learning snapshots"), so it inherits
  the new gate with no separate code or spec change.
- `session_allows_crypto` itself is **kept** for the weekend crypto *rebalance*,
  which deliberately stays scope-based.

### Interaction between the two fixes

They are complementary, not redundant. The valuation fix alone would make a wrongly
-included weekend snapshot read ~0 P&L (equities frozen at Friday's close), but it
would still emit a redundant snapshot row and push. The holdings gate suppresses that
noise. Together: de-facto stocks-only sessions are skipped on weekends, and any
session that *is* snapshotted when the market is closed is valued at the last close
for its equities.

## Risks / Trade-offs

- **Close lookup inside a read request**: mitigated by preferring stored closes and,
  when fetching, batching over the session's tickers with a short window; it only
  happens while the market is closed, and degrades to the old behavior on failure.
- **Classifying crypto vs equity at the valuation seam**: reuses the existing
  category discriminator; if a position's asset row is missing a category it is
  treated as equity (the conservative default — subject to the close/quote/avg-cost
  fallback anyway).
- **Holidays**: `is_market_open()` already reflects market holidays, so a weekday
  holiday is valued at the last close too — a strict improvement, with no new
  holiday calendar introduced.
- **A crypto-allowed but crypto-flat session is skipped on a weekend**: intended
  (its value does not move); narrowable at review to "scope includes crypto AND holds
  crypto" if desired.

## Migration Plan

No schema change, no migration, no data backfill. Pure behavior change in
`compute_session_value` (+ its marking helper) and the weekend snapshot selection.
Rollback is reverting the code; stored snapshots are unaffected in shape.

## Open Questions

- **Primary close source**: stored `price_history` closes vs
  `fetch_daily_closes`. Does `price_history` already ingest daily closes for all
  *held* tickers, or only benchmarks? If held-ticker closes are stored, read them;
  otherwise fetch a bounded trailing window. Resolved during apply against the
  `price_history` service.
- **Weekend gate breadth**: holdings-only (recommended, in the spec) vs "scope
  includes crypto AND holds crypto." Defaulting to holdings-only; confirm at review.
