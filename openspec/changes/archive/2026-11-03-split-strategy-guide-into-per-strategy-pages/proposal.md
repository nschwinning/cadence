## Why

The strategy guide at `/bots/strategies` is a single page that hardcodes the lone
`ma_crossover` catalog entry, so it cannot scale: adding a second strategy to the bots
catalog would not produce a second page, and the one-size page mixes a specific
strategy's mechanic with the strategy-agnostic capital/risk documentation. We want one
page per strategy so new strategies get their own page with no rework.

## What Changes

- Turn `/bots/strategies` into an **index** that lists **every** strategy from the bots
  catalog as a card (display name + short blurb), each linking to that strategy's own
  detail page.
- Add a **per-strategy detail page** at `/bots/strategies/:key` that resolves the catalog
  entry by key and shows that strategy's explanation text plus its illustrative chart
  (when one exists for that strategy). An unknown/missing key shows a not-found state.
- Make the illustrative chart **strategy-specific** via a small client-side registry keyed
  by strategy key (the existing MA-Crossover synthetic chart is registered for
  `ma_crossover`); a strategy with no registered chart renders explanation-only.
- Document the **strategy-agnostic capital & risk controls** (ATR risk-based sizing,
  per-name cap, max concurrent positions, shared budget ceiling, take-profit, stop-loss,
  drawdown kill-switch) **once** in a shared "Capital & risk" section on the index — no
  longer repeated per strategy, and not shown on the detail pages.
- Point the existing "Strategy guide" affordance in the Bots area at the index, and keep
  loading/error states for both the index and the detail page.

No backend, API, catalog, or schema change — the catalog already exposes each strategy's
`key`, `display_name`, and `explanation`. This is a frontend restructuring of an existing
`app-shell` requirement; no new strategy is added.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The "Strategy explanation navigation entry and page" requirement changes
  from a single hardcoded strategy page to an **index of all catalog strategies** plus a
  **per-strategy detail page**, with the capital-management/risk-control documentation
  written once in a shared section rather than per strategy.

## Impact

- **Frontend only.** `frontend/src/pages/bots/StrategiesPage.tsx` splits into an index view
  and a per-strategy detail view (plus a client-side strategy→chart registry); routes in
  `frontend/src/App.tsx` add `/bots/strategies/:key` alongside the existing
  `/bots/strategies` (both already ordered before `bots/:id`); the "Strategy guide" link in
  `frontend/src/pages/bots/BotsPage.tsx` targets the index. Reuses the existing
  `crossoverChart.ts`, `useStrategies()` hook, and the six risk-control cards' content.
- No backend, API, database, or dependency changes.
