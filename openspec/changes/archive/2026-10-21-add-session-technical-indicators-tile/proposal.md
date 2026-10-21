# Add a Technical-indicators fact tile to the session detail view

## Why

A paper-trading session carries a `use_technical_indicators` opt-in that is chosen
at build time and frozen on the session — when enabled, the build and every
rebalance only enter assets in a confirmed uptrend and attach trend context to
holdings. Every sibling build-time opt-in is echoed back read-only on the session
detail page (`/portfolios/:id`): Stop-loss, Risk guardrails, Learning feedback,
Company fundamentals, Watchlist assets, and Model each render a fact tile in the
session header. The technical-indicator strategy is the one opt-in with **no**
tile, so a user cannot tell from the session whether it is trading on the
trend-following strategy. This closes that gap for consistency.

## What Changes

- The session detail header (`PaperTradingSessionPage.tsx`) gains a read-only
  **Technical indicators** fact tile showing `On`/`Off` from the session's
  `use_technical_indicators` flag, mirroring the existing Company fundamentals and
  Watchlist assets tiles.
- No backend, schema, migration, or API change: `use_technical_indicators` is
  already returned on `PaperTradingSessionRead` and present on the TypeScript
  `PaperTradingSession` type.

## Capabilities

- `app-shell` (MODIFIED): the "Portfolio and paper-trading views" requirement adds
  the session detail view's display of the technical-indicator configuration.

## Impact

- Frontend only: `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`
  (one fact tile) and its co-located test.
- No backend, database, or API surface is touched.
