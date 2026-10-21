## 1. Backend — shared P&L triple + range helpers

- [x] 1.1 In `paper_trading/service.py`, add a helper that returns a session's live triple `(current_value, realised_pnl, unrealised_pnl)` reusing `compute_session_value` for current value + live unrealised and `session.total_pnl` for cumulative realised (all-time basis), so the list read and detail KPIs derive the triple from one place. Keep it lighter than `session_kpis` (no Sharpe/benchmark/time-weighted work).
- [x] 1.2 Add a range-realised helper: sum `ClosedPosition.realized_pnl` for lots whose `exit_date` is within `(range_start, range_end]`, using the `(session_id, exit_date)` index; for an unbounded/`Max` window it equals `session.total_pnl`.
- [x] 1.3 Add a range-unrealised helper: `current_live_unrealised − baseline`, where `baseline` is the summed per-position `unrealized_pnl` from the session's `SessionValueSnapshot` at or before `range_start` (0 when no such snapshot / `Max`). Reuse an existing snapshot lookup; do not add a migration.
- [x] 1.4 Backend tests (paper_trading): range realised = Σ closed-lot realised within range; range unrealised = live − range-start-snapshot unrealised; `Max`/unbounded reduces to cumulative realised (= `total_pnl`) and full current unrealised; no-snapshot and new-session paths fall back to the current live unrealised. Use the StubBroker for deterministic quotes.

## 2. Backend — paper-trading session list/read marked to market

- [x] 2.1 Extend the paper-trading session read path so a listed/single session carries live `current_value`, `realised_pnl`, and `unrealised_pnl` (all-time) via the 1.1 helper, marking open positions to market at request time.
- [x] 2.2 Add the three fields to the session read schema in `api/schemas.py` (and update docstrings); map them explicitly in the router/service response. Keep existing fields (`total_pnl`, `allocated_capital`, `contributed_capital`, etc.) intact.
- [x] 2.3 Backend tests: listing sessions returns the live triple per row and reflects moved quotes (not the last stored snapshot); single-session read returns the same triple; empty/no-position session returns an all-cash current value with zero unrealised.

## 3. Backend — dashboard overview range realised/unrealised

- [x] 3.1 In `dashboard/service.py`, add range realised + range unrealised to `SessionPerformance` for each active session, computed over the overview's already-resolved range window using the 1.2 / 1.3 helpers (keep existing current value, range ΔNAV P&L, and range fees).
- [x] 3.2 Add the two fields to `DashboardSessionPerformance` in `api/schemas.py` and the explicit router mapping; update docstrings.
- [x] 3.3 Backend tests (dashboard overview): per-session range realised/unrealised emitted for a range; `Max` range reduces realised to cumulative and unrealised to current live; empty-system path still returns zeroed/empty without error.

## 4. Frontend — types + dashboard

- [x] 4.1 Mirror the new fields in `types/api.ts`: `DashboardSessionPerformance` gains range realised + unrealised; the paper-trading session read gains `current_value` + `realised_pnl` + `unrealised_pnl`.
- [x] 4.2 In `pages/dashboard/aggregate.ts`, sum the per-session range realised and range unrealised across the selected sessions (simple dollar sums), alongside the existing money-weighted totals; extend `fixtures.ts` + `aggregate.test.ts`.
- [x] 4.3 Update the Dashboard hero tiles to show: current value, realised P&L (range), unrealised P&L (range), range return %, and range fees — realised/unrealised sign-distinguished; replace the standalone range ΔNAV P&L tile with the realised/unrealised pair.
- [x] 4.4 Update the Dashboard portfolio leaderboard columns to: name, current value, range realised P&L, range unrealised P&L, range return %, range fees — realised/unrealised/return sign-distinguished.
- [x] 4.5 Frontend tests: hero tiles + leaderboard render the triple and recompute realised/unrealised when the range changes and when the session selection changes.

## 5. Frontend — Portfolios list + session detail

- [x] 5.1 In the Portfolios list (`PaperTradingPage.tsx`), add current value + realised P&L + unrealised P&L columns (all-time), replacing the lone profit/loss column; sign-distinguish realised/unrealised.
- [x] 5.2 In the session detail page (`PaperTradingSessionPage.tsx`), remove the redundant realised-only "Total P&L" header `<dl>` stat (keep Capital); the KPI row already shows the full triple.
- [x] 5.3 Frontend tests: list renders the triple columns from the session read fields; detail header no longer shows a duplicate "Total P&L".

## 6. Frontend — live ~30s refresh

- [x] 6.1 Add `refetchInterval: 30_000` to `useDashboardOverview`, `useSessions`, and `useSessionKpis` (mirror `useSessionOrderSync`); rely on the TanStack default `refetchIntervalInBackground: false` for background pause. Do not add global `QueryClient` defaults.
- [x] 6.2 Frontend tests (mock timers): each of the three hooks issues a recurring refetch at ~30s without a refetch storm; verify no global polling leaks to unrelated queries.

## 7. Frontend — dashboard scope-band reflow (Direction A)

- [x] 7.1 Reflow `DashboardPage.tsx` into three labelled scope bands: a **Portfolio value** band (point-in-time/live), a **Performance** band (all range-scoped content: hero performance tiles, equity curve), and a **Universe** band (current-composition balance). Move the range selector out of the page title and dock it inside the Performance band's header, with a trailing active-range phrase (`today` / `the past week` / `the past month` / `year to date` / `the past year` / `all time`) derived from the selected range.
- [x] 7.2 Split `HeroTiles` into a value group (current value, marked live via the existing `FreshnessBadge kind="live"` chip + "updated every ~30s" tooltip) and a performance group (range realised, range unrealised, range return, range fees), placed in the value band and performance band respectively per 4.3.
- [x] 7.3 In `PortfolioLeaderboard`, add a spanning sub-header (e.g. "Over the past month") over the range-scoped columns (realised, unrealised, return, fees) and a single live `●` marker on the Value column header, so the point-in-time value reads as distinct from the range columns.
- [x] 7.4 In the Dashboard universe section, mark the balance summary as current composition ("as it stands now") and attach a range chip to the best/worst performers sub-block so it reads as range-scoped even beside the range-independent balance summary.
- [x] 7.5 Frontend tests: the range selector renders within the Performance band (not beside the page title); the active-range phrase tracks the selector; the value band shows the live chip and the current value does not change on range change; the universe performers carry a range chip while the balance summary does not change with the range.

## 8. Verify

- [x] 8.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 8.2 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 8.3 `openspec validate unify-range-relative-pnl-and-live-refresh --strict` passes.
