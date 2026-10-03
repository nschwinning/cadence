## Why

A paper-trading session shows headline KPIs and a value chart, but nothing tells the
user **where** their performance came from: which sectors and which asset categories
made or lost money. The asset-universe page already visualises a by-sector and
by-category split of the universe (the donut tiles), and the user wants the analogous
insight for an individual portfolio — but focused on **performance attribution**, not
just composition.

## What Changes

- **Per-session sector/category performance breakdown (backend).** A new read that,
  for one session, groups the session's realised and unrealised profit/loss by the
  held assets' **sector** and **category**, producing — per group — total P&L
  (realised + unrealised), its realised and unrealised components, the current market
  value of open positions in that group (for weight context), and a return percentage
  for the group (or unavailable when its cost basis is zero). This requires a new
  join from paper-trading holdings/closed positions to the asset catalogue (by
  ticker), which does not exist today.
- **Robust grouping.** Assets with no sector (crypto, most ETFs) are grouped under a
  "No sector" bucket; a position whose ticker no longer matches any catalogue asset is
  grouped under "Unknown", so the breakdown never drops P&L or fails.
- **Session-detail performance view (frontend).** A new card on the paper-trading
  session detail page showing the by-sector and by-category performance. Because P&L
  can be **negative**, this uses a **signed** presentation (per-group rows / diverging
  bars with gain/loss colouring and a return %), not a donut — donuts cannot represent
  negative contributions.

## Capabilities

### New Capabilities

_None._ This change extends existing capabilities.

### Modified Capabilities

- `ai-paper-trading`: add a requirement for a **per-session sector/category
  performance breakdown** — grouping realised + unrealised P&L (and market value and
  return %) by the held assets' sector and category via a ticker→asset join, with
  defined handling for assets lacking a sector and for tickers with no matching asset.
- `app-shell`: add a requirement for a **session-detail sector/category performance
  card** that presents the breakdown with sign-aware P&L and return %.

## Impact

- **Backend**: `paper_trading/service.py` (new aggregation function reusing
  `compute_session_value` for mark-to-market and `get_closed_positions` for realised
  P&L, plus the new ticker→`Asset` join — normalising tickers to the catalogue's
  casing); `api/schemas.py` (new breakdown-entry + response schema);
  `api/routers/paper_trading.py` (new `GET /sessions/{id}/sector-performance`, 404 on
  unknown session). **No DB migration** — pure read/join.
- **Frontend**: `types/api.ts`, `api/paperTrading.ts` (new typed client + hook), and a
  new card component on `pages/paper-trading/PaperTradingSessionPage.tsx`, with a
  co-located Vitest test.
- **Decisions open to your review** (recorded in design.md): performance is defined as
  **total P&L = realised + unrealised**; the view is a **signed** presentation rather
  than a donut.
- No change to the order model, the rebalance flow, or `add-weekend-crypto-rebalance`.
