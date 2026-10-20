## 1. Navigation

- [x] 1.1 In `frontend/src/components/layout/Sidebar.tsx`, collapse the `NAV_ITEMS` "Portfolios" and "Paper Trading" entries into a single "Portfolios" entry pointing at `/portfolios` (keep the existing Portfolios icon, drop the Paper Trading icon); verify the nav renders one "Portfolios" item and no "Paper Trading" item (nav vitest).

## 2. Routing and redirects

- [x] 2.1 In `frontend/src/App.tsx`, point `/portfolios` at the unified list page and `/portfolios/:id` at the unified detail page (the repurposed paper-trading pages), and remove the `PortfoliosPage`/`PortfolioDetailPage` route imports; verify the two routes resolve and typecheck passes.
- [x] 2.2 In `frontend/src/App.tsx`, add a small redirect element that reads `useParams().id` and renders `<Navigate replace>` so `/paper-trading` → `/portfolios` and `/paper-trading/:id` → `/portfolios/:id` with the id preserved; verify both redirects via a routing vitest.

## 3. Unified list page

- [x] 3.1 Repurpose `frontend/src/pages/paper-trading/PaperTradingPage.tsx` as the unified Portfolios list: keep `<BuildAIPortfolioCard />` and `<SessionComparisonChart />` above the table, relabel the page/header to "Portfolios", and route row links to `/portfolios/:id` (session id); verify the list renders the build card, comparison chart, and sessions table (list vitest).
- [x] 3.2 Fold the portfolio-definition columns into the unified list table: for each session, resolve its portfolio (via the portfolios query) and show the portfolio's risk profile and holdings count alongside the existing Status, Capital, Trades, and P&L columns; verify a session row shows risk profile and holdings count (list vitest).
- [x] 3.3 Keep a single "Show archived" toggle and a single per-row archive action wired to the session archive/unarchive flow; verify the toggle reveals archived sessions and the row archive action archives a stopped session (list vitest).

## 4. Unified detail page

- [x] 4.1 In `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, resolve the session's portfolio via `usePortfolio(session.portfolio_id)` and render a folded-in portfolio Overview facts grid (Source, Risk profile, Max allocation, Holdings, Created, Source run id) plus a Holdings list whose tickers link to `/assets/:ticker`; verify the detail renders the Overview facts and holdings links (detail vitest).
- [x] 4.2 Make the portfolio block fail soft: when the session has no resolvable portfolio (no `portfolio_id` or the fetch 404s), render all session content and omit the portfolio-definition block without erroring; verify a session with no resolvable portfolio still renders session content and omits the block (detail vitest).
- [x] 4.3 Confirm the detail keeps the existing session archive card wired to the session archive flow (no separate portfolio-archive control); verify the archive card is present and no portfolio-archive control is rendered (detail vitest).

## 5. Remove dead portfolio pages

- [x] 5.1 Delete `frontend/src/pages/portfolios/PortfoliosPage.tsx` and `frontend/src/pages/portfolios/PortfolioDetailPage.tsx` (and their co-located tests), and remove any now-dead imports/`useSessions`-gating that only served the old portfolio-archive UI; verify `npm run -s typecheck` and `npm run build` succeed with no dangling imports.

## 6. Tests and verification

- [x] 6.1 Update or migrate the co-located vitest suites for the merged pages (nav, routing/redirect, unified list columns + archive + toggle, unified detail folded-in portfolio + fail-soft), keeping fixtures (which carry `include_watchlist`, `use_fundamentals`, etc.) consistent; retire tests for the deleted components.
- [x] 6.2 Run the full frontend gate `cd frontend && npm run -s typecheck && npx vitest run && npm run build` and verify all three pass.
- [x] 6.3 Run `openspec validate merge-portfolios-and-paper-trading --strict` and verify it passes.
