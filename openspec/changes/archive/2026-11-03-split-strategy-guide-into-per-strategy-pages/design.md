## Context

See proposal.md — Why. The current `frontend/src/pages/bots/StrategiesPage.tsx` is a
single route (`/bots/strategies`, registered in `App.tsx` before `bots/:id`) that calls
`useStrategies()`, finds the `ma_crossover` entry, and renders its `display_name` +
`explanation`, one `IllustrativeChart` (an `EChart` fed by `crossoverChart.ts`), and six
`RiskControl` cards, with `role=status` loading and `role=alert` error states. The bots
catalog endpoint already returns, per strategy, `key`, `display_name`, `required_history`,
`params_schema`, and `explanation` (mirrored by TS type `BotStrategyCatalogEntry`). Only
one strategy (`ma_crossover`) exists today. This change is a frontend-only restructuring.

## Goals / Non-Goals

**Goals:**

- `/bots/strategies` becomes an index over the whole catalog; each strategy gets its own
  `/bots/strategies/:key` detail page.
- The illustrative chart is selected per strategy, so a strategy without a chart still
  renders cleanly.
- The capital/risk documentation is authored once (on the index), not per strategy.
- Preserve existing loading/error behavior and add an unknown-key not-found state.

**Non-Goals:**

- No backend/API/catalog/schema change; no new strategy; no change to the sizing/capital
  model or to bot create/list/detail beyond the "Strategy guide" link target.
- No new routing or data-fetching library; reuse React Router and the existing
  `useStrategies()` hook.

## Decisions

### Index + detail split, both driven by the existing catalog hook

`/bots/strategies` renders an index component; `/bots/strategies/:key` renders a detail
component. Both call the existing `useStrategies()` query (already cached by TanStack
Query, so the detail page reuses the index's fetched catalog with no extra request). The
detail component reads `:key` via `useParams`, finds the matching catalog entry, and
renders explanation + optional chart.

- **Alternative considered:** a single page with client-side tabs/accordion per strategy.
  Rejected — the user explicitly wants one page (one URL) per strategy, and separate routes
  are linkable/bookmarkable and scale without a growing single component.

### Route registration order

Add `<Route path="bots/strategies/:key" …>` alongside the existing
`bots/strategies` index route, both kept **before** `bots/:id` so neither `strategies`
nor `strategies/:key` is captured by the `:id` param. `strategies` (exact) and
`strategies/:key` are distinct path depths, so they do not conflict with each other.

### Client-side strategy → illustrative chart registry

The illustrative chart is presentation-only synthetic data, not catalog data, so it stays
on the frontend. Introduce a small registry mapping a strategy `key` to an optional chart
descriptor (`{ buildOption, ariaLabel }`). The detail page looks the strategy up in the
registry; if present it renders the `EChart`, otherwise it renders explanation-only. The
existing `crossoverChart.ts` (`buildCrossoverChartOption`) is registered under
`ma_crossover` with the existing aria-label "Illustrative moving-average crossover with
entry and exit markers".

- **Alternative considered:** key the chart off a backend field. Rejected — keeps backend
  untouched (out of scope) and the synthetic illustration is inherently a frontend concern.

### Shared "Capital & risk" section lives on the index only

The six existing `RiskControl` cards (shared budget ceiling, ATR position sizing, per-name
cap, max concurrent positions, take-profit / stop-loss, drawdown kill-switch) move to a
"Capital & risk" section on the **index** page, reused verbatim. Detail pages do not render
them. This matches the user's choice to document strategy-agnostic controls once.

- **Alternative considered:** a dedicated `/bots/strategies/capital-risk` sub-page.
  Rejected as heavier than needed for a single shared section; a section on the index keeps
  the docs one click from the strategy list. (Revisit if the index grows large.)

### States

- **Index:** loading (`role=status`), error (`role=alert`), and empty (catalog loads but
  has no strategies → a friendly "no strategies" message instead of a blank list).
- **Detail:** loading, error, and **unknown key** — when the catalog loaded but holds no
  entry for `:key`, show a not-found state (with a link back to the index) rather than a
  blank page.

### Component/file shape

Split `StrategiesPage.tsx` into an index view and a detail view (either two files under
`pages/bots/` or one module exporting both components) plus the chart registry. Reuse the
existing `EChart` wrapper, `RiskControl` card, `useStrategies()` hook, and
`crossoverChart.ts`. The "Strategy guide" link in `BotsPage.tsx` keeps pointing at
`/bots/strategies` (the index).

## Risks / Trade-offs

- [Only one strategy exists, so the index shows a single card] → Acceptable; the structure
  is the point. The index still adds value today via the shared Capital & risk section, and
  scales the moment a second strategy is registered.
- [Route `:key` typo or stale link yields no catalog match] → Mitigated by the explicit
  unknown-key not-found state with a back-link, covered by a test.
- [Duplicated risk-doc content drifting if someone re-adds it to detail pages] → Mitigated
  by a test asserting the Capital & risk docs render on the index and NOT on the detail
  page.

## Open Questions

_None._
