# Add crypto trading

## Why

Cadence can only trade equities today. Alpaca supports crypto (BTC, ETH, …) on the
same paper/live account, and the asset universe already classifies each asset as
`stock`/`crypto`/… (`Asset.category`). But the engine bakes in equities-only
assumptions that silently break crypto:

- **Orders** default to `time_in_force="day"`, which crypto rejects (crypto takes
  `gtc`/`ioc` only).
- **Quotes** hit the equities-only `/v2/stocks/...` data endpoints; a crypto symbol
  returns an empty quote → no price → the ticker is skipped.
- **Sizing** is whole-share (`int(capital*weight/price)`), so a high-unit-price
  coin like BTC rounds almost every allocation to 0 and nothing trades.
- **Symbols** differ across systems: yfinance `BTC-USD`, Alpaca trading/data
  `BTC/USD`, and there is no translation layer, so positions never reconcile.
- **The rebalance market-open guard** skips the whole run when the equities market
  is closed, wrongly halting crypto, which trades 24/7.

## What Changes

- Add an `AssetClass` (equity/crypto) concept derived from the existing
  `Asset.category`; the asset record remains the single source of truth for whether
  a ticker is a stock or crypto. Thread the per-ticker class from the universe
  through the executor to the broker (no fragile symbol-sniffing in business logic).
- Add a pure symbol-translation module mapping the universe's canonical crypto
  format (`BTC-USD`) to Alpaca's (`BTC/USD`) and back; the broker returns positions
  in canonical form so they reconcile with the universe.
- Route crypto **orders** with a crypto-compatible time-in-force (`gtc`) and
  fractional quantities; route crypto **quotes** to Alpaca's
  `/v1beta3/crypto/...` endpoints.
- Size crypto positions **fractionally**, skipping only below the brokerage minimum
  notional (~$1) instead of below one whole share.
- Make the daily rebalance **crypto-aware around the clock**: when the equities
  market is closed, still rebalance crypto and skip only equity orders; record a
  skipped run only when nothing is tradable.
- No database migration: `paper_trades.quantity` / `closed_positions.quantity` are
  already `Float`, and `Asset.category` already carries `crypto`.

## Impact

- Affected specs: `ai-paper-trading` (order/quote/sizing/rebalance behavior),
  `assets` (crypto classification is a first-class, tradable state).
- Affected code: `broker/models.py`, `broker/base.py`, `broker/alpaca.py`,
  `broker/stub.py`, new `broker/symbols.py`; `ai_portfolio/executor.py`,
  `ai_portfolio/service.py`, `ai_portfolio/agent.py` (prompt); backend tests.
  Minimal/no frontend change (fractional quantities already render; trades/events
  are generic).
- No schema/migration change.
