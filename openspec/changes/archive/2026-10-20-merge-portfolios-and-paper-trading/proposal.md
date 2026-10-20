## Why

The app has two separate nav areas — "Portfolios" and "Paper Trading" — that are really two views of the same objects. The only way to create a portfolio in the UI is the build card, which simultaneously opens a paper-trading session, so the two lists are effectively a 1:1 pairing: the Portfolios list shows the *definition* (holdings, risk, source) while the Paper Trading list shows the *performance* (capital, trades, P&L, status) of the same thing. The two list pages are near-duplicate scaffolding, neither detail page links to the other, and users must bounce between them to see one portfolio's full picture. Merging them into one "Portfolios" area removes the redundancy and gives each portfolio a single home.

## What Changes

- **BREAKING (navigation):** The "Paper Trading" nav item is removed. A single **"Portfolios"** nav item is the entry point for the merged area.
- The unified **Portfolios list** is session-driven: it is the paper-trading sessions list (status, capital, trades, P&L), relabeled "Portfolios", with the portfolio-definition columns (risk profile, holdings count) folded in. It keeps the build card and the multi-session comparison chart at the top, one "Show archived" toggle, and one per-row archive action (archive the session).
- The unified **Portfolios detail** page (`/portfolios/:id`, where `:id` is the **session** id) is the rich session detail page — value chart, KPIs, sector performance, trades, runs, closed positions, rebalance/close/archive controls, AI event history — **enriched** by folding in the portfolio *definition* content: an Overview facts grid (source, risk profile, max allocation, holdings, created, source run id) and a Holdings list whose tickers link to each asset. The portfolio is resolved via the session's `portfolio_id`.
- The separate standalone **portfolio list page**, **portfolio detail page**, and the old **paper-trading list page** are retired from the UI.
- **Single archive control:** the merged area's archive action archives/unarchives the **session** (the existing session-archive flow). The portfolio-archive UI is removed. Portfolio backend records and endpoints are untouched.
- **Old routes redirect:** `/paper-trading` → `/portfolios` and `/paper-trading/:id` → `/portfolios/:id` (param preserved), so existing bookmarks and in-app links keep working.
- **Scope is frontend-only:** no backend, API, schema, or migration changes. Both `/api/v1/portfolios` and `/api/v1/paper-trading/sessions` endpoints and their query clients remain as-is.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The navigation, routing, and views requirements change to describe a single merged "Portfolios" area — one nav item (no "Paper Trading"), the session-driven unified list page (with folded-in portfolio columns, build card, comparison chart, single session-archive action), the unified detail page that folds the portfolio definition into the session detail, and redirects from the old `/paper-trading` routes.

## Impact

- **Frontend routing** (`src/App.tsx`): the four portfolio/paper-trading routes collapse to `/portfolios` (unified list) and `/portfolios/:id` (unified detail), plus `<Navigate replace>` redirects from `/paper-trading` and `/paper-trading/:id`.
- **Frontend nav** (`src/components/layout/Sidebar.tsx`): the "Portfolios" and "Paper Trading" `NAV_ITEMS` entries collapse to one "Portfolios" item.
- **Frontend pages**: the paper-trading list and detail pages become the unified pages (enriched with the portfolio definition); `PortfoliosPage`, `PortfolioDetailPage`, and the old paper-trading list page are removed. `BuildAIPortfolioCard` moves with the build entry point onto the unified list.
- **Frontend tests** (co-located Vitest): nav, routing/redirect, unified list, and unified detail tests updated; tests for removed pages retired.
- **No backend impact:** portfolio and session APIs, query keys, and data shapes are unchanged.
