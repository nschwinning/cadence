## Context

See `proposal.md` — Why. This is a frontend-only UI reorganization: two sibling nav areas ("Portfolios" and "Paper Trading") that are effectively a 1:1 pairing (the build card creates a `Portfolio` and a `PaperTradingSession` together) collapse into one "Portfolios" area.

Current frontend seams (grounded by exploration):

- **Router** (`frontend/src/App.tsx`, lines ~25-28, imports ~7-10): four routes — `portfolios` → `PortfoliosPage`, `portfolios/:id` → `PortfolioDetailPage`, `paper-trading` → `PaperTradingPage`, `paper-trading/:id` → `PaperTradingSessionPage`.
- **Nav** (`frontend/src/components/layout/Sidebar.tsx`, `NAV_ITEMS` lines ~27-48): order Dashboard, Assets, Watchlist, Portfolios, Paper Trading, Runs, Technical Indicators, System. Nav lives only in the sidebar; `Header.tsx` only toggles the off-canvas sidebar.
- **Portfolios list** (`pages/portfolios/PortfoliosPage.tsx`): renders `<BuildAIPortfolioCard />` + a "Stored portfolios" table (Name→`/portfolios/:id`, Source, Risk, Holdings count, Max Alloc %, Created, Archive) + "Show archived" toggle; calls `useSessions()` only to gate the portfolio-archive action with an "In use" badge.
- **Portfolio detail** (`pages/portfolios/PortfolioDetailPage.tsx`): thin Overview facts grid (Source, Risk profile, Max allocation, Holdings, Created, Source run id) + Holdings list linking tickers to `/assets/:ticker`.
- **Paper-trading list** (`pages/paper-trading/PaperTradingPage.tsx`): renders `<SessionComparisonChart />` + a "Sessions" table (Portfolio=`portfolio_name||strategy_key`→`/paper-trading/:id`, Status, Schedule, Capital, Trades, P&L, Last Run, Archive) + "Show archived" toggle.
- **Session detail** (`pages/paper-trading/PaperTradingSessionPage.tsx`, ~43KB): value chart, KPIs, sector performance, trades, runs, closed positions, rebalance/close/archive cards, AI event history; title = `session.portfolio_name` (line ~625); no portfolio link today.
- **Data shapes** (`types/api.ts`): `Portfolio` has id/name/stocks[]/max_allocation_pct/source/risk_profile/source_run_id/created_at/archived_at (no capital/value). `PaperTradingSession` has `portfolio_id` (FK), nullable `portfolio_name`, strategy_key, status, capital, trades, pnl, archived_at, … A session belongs to a portfolio via `portfolio_id`.
- **Query clients**: `api/portfolios.ts` (`portfolioKeys`, `usePortfolio`) and `api/paperTrading.ts` (`paperTradingKeys`, `useSessions`, session archive mutation). Both API namespaces stay.

## Goals / Non-Goals

**Goals:**

- One "Portfolios" nav entry and one session-driven list page that carries the portfolio-definition columns (risk profile, holdings count).
- One detail page at `/portfolios/:id` (`:id` = session id) that is the rich session page with the portfolio *definition* (Overview facts + Holdings list) folded in.
- One archive action (session archive) in the merged area; legacy `/paper-trading*` links keep working via redirect.
- Minimal file churn; no backend/API/schema/migration changes.

**Non-Goals:**

- No change to the build flow, KPIs, charts, rebalance/close controls, or any backend endpoint, query key, or data shape.
- No portfolio-archive behavior change on the backend (the `/api/v1/portfolios` archive endpoint stays; only its UI entry point is removed).
- No merge of the two *data models* — `Portfolio` and `PaperTradingSession` remain distinct; the detail page simply fetches both.

## Decisions

**1. The unified list is the paper-trading sessions list (session-driven), relabeled.**
The sessions list is the richer surface (status, capital, trades, P&L, comparison chart) and is keyed by the object users actually operate on. We fold the two portfolio-definition columns (risk profile, holdings count) into it rather than the reverse. *Alternative considered:* driving the list from portfolios and hanging session stats off each row — rejected because it would invert the richer page into the thinner one and lose the session-keyed routing the detail page already uses.

**2. File layout: repurpose the paper-trading pages as the merged pages; delete the three now-dead components.**
Rename/retarget `PaperTradingPage.tsx` → the unified list and `PaperTradingSessionPage.tsx` → the unified detail (keep their file paths to minimize churn in the large 43KB session file and its many co-located chart/card components), route both under `/portfolios*`, and delete `PortfoliosPage.tsx` + `PortfolioDetailPage.tsx`. `BuildAIPortfolioCard.tsx` moves with the build entry point onto the unified list (it already lives under `pages/portfolios/` and is imported by the list). *Alternative considered:* building brand-new unified page files and deleting all four — rejected as needless churn on the largest, most test-covered file. *Assumption (minor):* keeping the session page's existing title (`portfolio_name`) as the merged detail title.

**3. Detail folds in the portfolio definition, resolved by `session.portfolio_id`.**
The merged detail calls `usePortfolio(session.portfolio_id)` and renders an Overview facts grid (Source, Risk profile, Max allocation, Holdings, Created, Source run id) + a Holdings list whose tickers link to `/assets/:ticker` — the content previously on `PortfolioDetailPage`. *Fail-soft:* when the session has no resolvable portfolio (no `portfolio_id`, or the fetch 404s), the detail still renders all session content and simply omits the portfolio-definition block rather than erroring. This preserves the spec's "fails soft" scenario and tolerates the rare portfolio-less session.

**4. Single archive = session archive; remove the portfolio-archive UI.**
The merged list's row archive action and the detail's archive card use the existing session archive/unarchive flow (`paperTradingKeys`/session archive mutation). The portfolio-archive action and the "In use" gating that `PortfoliosPage` needed are deleted. The portfolio backend archive endpoint is untouched (out of frontend scope) — it simply loses its UI trigger. *Rationale:* a session is the thing with lifecycle state (stopped/active/paused) that archiving is gated on; the portfolio archive flag becomes vestigial in the UI but harmless.

**5. Redirects via React Router `<Navigate replace>`, preserving `:id`.**
`/paper-trading` → `/portfolios`; `/paper-trading/:id` → `/portfolios/:id` with the param carried through (a small redirect element reads `useParams().id` and renders `<Navigate to={...} replace />`). `replace` keeps the stale URL out of history. *Alternative considered:* server-side redirect — rejected (frontend-only scope; the SPA owns routing).

**6. Keep the existing app-shell requirement names when editing the spec.**
The MODIFIED requirements retain their current titles ("Portfolio and paper-trading views", "Archive controls for sessions and portfolios") even though "paper-trading" is now imprecise, to minimize sync/validation churn; the bodies carry the merge semantics. The comparison-chart and build-form requirements are left unmodified — their behavior is unchanged and they simply render inside the unified list; `design` records that the "paper-trading session list view" they reference is now realized by the unified Portfolios list.

## Risks / Trade-offs

- **Stale deep links / bookmarks to `/paper-trading*`** → Mitigated by the two `<Navigate replace>` redirects preserving `:id`; covered by a redirect vitest.
- **A session with no resolvable portfolio could crash the enriched detail** → Mitigated by the fail-soft decision (#3): omit the portfolio block, never throw; covered by a "no resolvable portfolio" vitest.
- **Deleting `PortfoliosPage`/`PortfolioDetailPage` could orphan imports or their co-located tests** → Mitigated by updating `App.tsx` imports in the same change and retiring/migrating the deleted pages' tests; the typecheck + build gates catch any dangling import.
- **Requirement titles now read "paper-trading" for a merged area** → Accepted trade-off (decision #6) to keep the spec delta low-risk; bodies are authoritative.
- **`portfolioKeys` cache no longer invalidated by a portfolio-archive action** → No risk: the action is removed, and `BuildAIPortfolioCard` still invalidates `portfolioKeys.all` on build, so the list's folded-in portfolio columns stay fresh.
