## 1. Strategy → illustrative-chart registry

- [x] 1.1 Add a client-side registry (e.g. `frontend/src/pages/bots/strategyCharts.ts`) mapping a strategy `key` to an optional chart descriptor `{ buildOption, ariaLabel }`, registering `ma_crossover` → `{ buildCrossoverChartOption, "Illustrative moving-average crossover with entry and exit markers" }` from the existing `crossoverChart.ts`, and exposing a lookup that returns `undefined` for an unregistered key; verify a Vitest unit test that the lookup returns the MA-Crossover descriptor for `ma_crossover` and `undefined` for an unknown key.

## 2. Index page (list + shared capital/risk docs)

- [x] 2.1 Build the strategy guide **index** at `/bots/strategies`: call `useStrategies()`, render one card per catalog strategy (display name + a short blurb derived from the catalog `explanation`), each card linking to `/bots/strategies/:key`; render the shared "Capital & risk" section reusing the existing six `RiskControl` cards verbatim; include loading (`role=status`), error (`role=alert`), and empty-catalog states. Verify a Vitest test that the index lists the catalog strategies, links each to its `/bots/strategies/:key` page, and renders the Capital & risk docs once.
- [x] 2.2 Verify a Vitest test for the index loading and error states (loading shows a status while the catalog is pending; a failed catalog request shows an alert instead of the list).

## 3. Per-strategy detail page

- [x] 3.1 Build the per-strategy **detail** page at `/bots/strategies/:key`: call `useStrategies()`, resolve the catalog entry by the `:key` route param, render its `display_name` + `explanation` (whitespace-pre-line) and, when the chart registry has a descriptor for the key, the illustrative `EChart` (with its registered aria-label); render explanation-only when no chart is registered; do NOT render the shared capital/risk docs here. Verify a Vitest test that the detail page for `ma_crossover` renders the explanation and the illustrative chart (and that the capital/risk docs are absent).
- [x] 3.2 Add the detail-page loading, error, and **unknown-key not-found** states (unknown key = catalog loaded but no entry for `:key` → a not-found message with a link back to the index). Verify a Vitest test for the unknown-key not-found state and for the loading/error states.

## 4. Routing & navigation wiring

- [x] 4.1 Register `/bots/strategies/:key` in `frontend/src/App.tsx` alongside the existing `/bots/strategies` index route, both kept before `bots/:id`; ensure the "Strategy guide" affordance in `BotsPage.tsx` points at the index. Verify via `npm run typecheck` and a Vitest test (or the index test) that navigating a strategy card reaches the detail route.

## 5. Verification gates

- [x] 5.1 Frontend green: `cd frontend && npm run typecheck && npm run test && npm run build`.
- [x] 5.2 Spec/change valid: `openspec validate split-strategy-guide-into-per-strategy-pages --strict`.
