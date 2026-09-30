## 1. Backend KPI computation

- [x] 1.1 Add a pure helper (e.g. `max_drawdown(values: Sequence[float]) -> float | None`) in `paper_trading/service.py` that returns the largest peak-to-trough decline as a non-negative fraction of the running peak over a date-ordered value series, None for an empty series, 0.0 for a never-declining series, and guards a non-positive peak; verify unit tests cover: rise-then-fall series returns the deepest drop, monotonic-rise returns 0.0, empty returns None.
- [x] 1.2 Add a pure helper (e.g. `closed_position_stats(pnls: Sequence[float])`) that returns win rate (fraction with pnl > 0, over all closed positions), average win (mean of pnl > 0), average loss (mean of pnl < 0), best (max), and worst (min) — each None when its input side is empty (no positions → all None; no winners → avg win None; no losers → avg loss None); verify unit tests cover mixed, all-winners, all-losers, and empty.
- [x] 1.3 Extend the `SessionKpis` dataclass and `session_kpis()` to populate `max_drawdown`, `win_rate`, `average_win`, `average_loss`, `best_trade`, `worst_trade` using the two helpers — drawdown from the ordered `list_value_snapshots` `total_value` series, the trade stats from the session's `ClosedPosition.realized_pnl` rows; verify `session_kpis()` tests assert the six fields for a session with snapshots + closed positions and assert None where inputs are absent.

## 2. API + type surface

- [x] 2.1 Add the six nullable fields (`float | None`) to `PaperTradingSessionKpisRead` in `api/schemas.py` and confirm `get_session_kpis` maps them through; verify the KPI endpoint test asserts the fields appear in the response payload.
- [x] 2.2 Mirror the six fields on `PaperTradingSessionKpis` in `frontend/src/types/api.ts` (as `number | null`); verify `npm run typecheck` passes.

## 3. Frontend tiles

- [x] 3.1 Restructure `KpiRow` in `PaperTradingSessionPage.tsx` into two labeled groups (see `design-tiles.md`): keep the existing 8 tiles under a "Performance" `<h3>` and grid (`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4`), and add a new "Risk & trade quality" `<h3>` + grid (`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3`); each group gets `role="group"` + `aria-labelledby` pointing at its heading id (`h3` = `text-sm font-semibold uppercase tracking-wide text-slate-500`); verify the session-page test finds both group headings.
- [x] 3.2 Add the six new `StatTile`s to the "Risk & trade quality" group in order — Maximum drawdown, Win rate, Average win, Average loss, Best trade, Worst trade — reusing existing helpers (`PnlValue`, `pnlClass`, `formatCurrency`, `formatPercent`); apply the sign rules: render max drawdown with an explicit leading `−` and red when non-zero (neutral `0.00%` when zero, never `abs()`-ed to look like a gain), render average loss / worst trade as their signed raw currency (leading `-$`, not absolute), color best/worst by actual sign via `PnlValue`, and keep win rate neutral (no P&L color); verify the session-page test asserts the drawdown minus-sign and sign-colored trade values.
- [x] 3.3 For each new tile, render the null case exactly like the existing null-Sharpe tile — value string `'Not yet available'` plus an explanatory hint (drawdown: "Needs a value snapshot"; win rate / best / worst: "No closed positions yet"; average win: "No winning positions yet"; average loss: "No losing positions yet"); verify a session-page test with an empty session shows the placeholders and hints.

## 4. Verification

- [x] 4.1 Run the full backend suite (`uv run pytest`), `uv run ruff check .`, and `uv run mypy src/cadence`, and the frontend (`npm run typecheck`, `npx vitest run`); verify all are green and `openspec validate add-session-drawdown-winrate-kpis --strict` passes.
