## Why

Watchlist assets are, by design, *emerging* companies that fail the universe
maturity bar (stocks need ≥ 5 years of history, crypto ≥ 1 year; most watchlist
names have under 1–2 years, often under 1). The existing technical-indicator
suite centers on a long-window uptrend "trend gate" that depends on SMA200 and
its 20-day slope (~220 trading days). For young names those inputs are absent, so
the gate fails and the long-window indicators blank out — making the current
suite the wrong tool for exactly the assets on the watchlist. Short-window
momentum/mean-reversion indicators (RSI, MACD, EMA, Bollinger) are meaningful
with only ~1–2 months of data and are the right fit for watching emerging names.

This is **phase 1** of a two-phase idea: compute and *display* a short-window
technical profile for watchlist assets. Making watchlist assets *tradable*
against those indicators is explicitly deferred to a later change.

## What Changes

- Extend the nightly technical-indicator computation job so it also computes and
  stores a snapshot for **watchlist** assets, not just universe assets. The
  compute engine itself is unchanged (it is already ticker-agnostic and
  close+volume-only).
- Define a **short-window profile** as the meaningful indicator subset for
  watchlist assets: RSI (14), MACD line/signal/histogram (12/26/9), EMA (20),
  Bollinger %b + bandwidth (20, 2σ), 20-day historical volatility, volume ratio
  vs the 50-day average, OBV 20-day change, and the reversal flags whose inputs
  are all short-window. The long-window indicators (SMA 50 / SMA 200 and their
  ratios, SMA200 slope, ROC 120, 52-week-high distance, 252-day drawdown) and the
  derived uptrend **trend-gate verdict** SHALL NOT be presented as a trading
  signal for watchlist assets.
- Apply a **minimum-history floor** (a tunable constant, proposed at ~40 daily
  bars): a watchlist asset below the floor is recorded with an
  *insufficient-history* marker instead of a snapshot of mostly-absent values.
- Surface the short-window profile per entry on the **Watchlist page**, with an
  explicit "insufficient history" state below the floor.
- **Not changing trading.** The invariant that watchlist assets never enter
  trading/analytics reads (trading candidates come from `list_assets`, which
  defaults to `membership=universe`) stays fully intact.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `technical-indicators`: the nightly computation job now also covers watchlist
  assets; a new requirement defines the watchlist short-window profile, the
  minimum-history floor / insufficient-history marker, and that the long-window
  trend-gate verdict is not a watchlist trading signal.
- `app-shell`: the Watchlist view surfaces each entry's short-window
  technical-indicator profile alongside its fundamentals, with an explicit
  insufficient-history state.

## Impact

- **Backend**: `technical_indicators/service.py` (nightly runner now iterates
  watchlist membership; read/surfacing of the short-window subset +
  insufficient-history marker), `technical_indicators/constants.py` (new
  minimum-bars floor + short-window profile definition),
  `technical_indicators/models.py` + one additive nullable Alembic migration for
  a `bar_count` column (storage seam decided — design.md D3),
  `api/schemas.py` + the technical-indicators router/read path.
- **Frontend**: `pages/watchlist/WatchlistPage.tsx` (new per-entry technical
  panel + insufficient-history state), `api/assets.ts` or a technical-indicators
  client, `types/api.ts`.
- **Explicitly out of scope**: `flows/build.py`, `flows/rebalance.py`,
  `list_assets` trading defaults, the `use_technical_indicators` session flag,
  the universe trend gate, new long-window indicators, and any crypto-specific
  handling beyond what already exists.
