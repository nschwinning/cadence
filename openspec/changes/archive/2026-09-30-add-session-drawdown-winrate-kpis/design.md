## Context

Session KPIs are computed on read by `session_kpis()` in `paper_trading/service.py` (returns the `SessionKpis` dataclass), surfaced via `PaperTradingSessionKpisRead` (`api/schemas.py`) at `GET /sessions/{id}/kpis`, mirrored in `types/api.ts` (`PaperTradingSessionKpis`), and rendered by `KpiRow` on `PaperTradingSessionPage.tsx`. The inputs the new metrics need are already persisted: `SessionValueSnapshot.total_value` (one row per session per day, ordered via `list_value_snapshots`, oldest-first) and `ClosedPosition.realized_pnl` (one row per fully-exited position). No new persistence is involved. See proposal.md — Why.

## Goals / Non-Goals

**Goals:**
- Compute six additional figures on read from existing data, with explicit absent (None) semantics.
- Keep the change confined to the existing KPI read path and the session-detail tiles.

**Non-Goals:**
- No new columns, migration, config, or change to snapshot/closed-position recording.
- No exposure on the multi-session comparison list.
- No per-trade (per-sell) win definition — win rate is over closed positions (round-trips).

## Decisions

- **Maximum drawdown definition**: iterate the date-ordered `total_value` series, track the running peak, and take the maximum of `(peak - value) / peak` over all points; report as a non-negative fraction. Rationale: a value-based (NAV) drawdown matches how the value chart and Sharpe already treat the snapshot series. Alternative considered — drawdown from `daily_pnl_pct` cumulative returns — rejected as more error-prone and redundant with the stored `total_value`. Edge cases: no snapshots → None; a never-declining series → 0.0; a peak of 0 is not divided into (guarded).
- **Win rate / averages / extremes basis**: computed over `ClosedPosition` rows via `realized_pnl`. Winners are `realized_pnl > 0`, losers `realized_pnl < 0`; positions with exactly zero realized P&L count in the denominator of win rate but in neither average. Rationale: matches the user-confirmed "closed positions" unit and avoids double-counting partial exits.
- **Absent semantics**: every new field is `float | None`. drawdown → None with no snapshots; win rate/best/worst → None with no closed positions; average win → None with no winners; average loss → None with no losers. Rationale: None distinguishes "not enough data" from a real 0.0, consistent with how `sharpe_ratio` already returns None below its minimum.
- **Sign of average loss / worst trade**: reported as the raw realized P&L (negative for losses), not absolute value, so the tile shows the actual signed amount.
- **Frontend rendering** (full tile spec in `design-tiles.md`): split the single `KpiRow` grid into two labeled groups — the existing 8 tiles under "Performance" (`lg:grid-cols-4`) and the six new ones under "Risk & trade quality" (`lg:grid-cols-3`, so 6 tiles never leave a ragged row), each group an `<h3>`-labeled `role="group"`. Reuse the existing `StatTile`, `PnlValue`, `pnlClass`, `formatCurrency`, `formatPercent` — no new component or Tailwind token. Format drawdown and win rate as percentages, the four trade figures as currency. Max drawdown arrives as a non-negative magnitude, so display it with an explicit leading `−` and red when non-zero (neutral `0.00%` when flat) rather than an unsigned percent that reads like a gain; average loss and worst trade are already-signed raw P&L and render unchanged (leading `-$`, never `abs()`-ed); best/worst are colored by their actual sign. Win rate stays neutral (no P&L color). Null values render exactly like the current null-Sharpe tile: value `'Not yet available'` plus an explanatory hint. Every sign is also textual (leading `−`, `-$`, labels) so nothing relies on color alone (WCAG-safe; all colors are existing AA-passing tokens).

## Risks / Trade-offs

- [Drawdown granularity is daily] → Intraday dips between end-of-day snapshots are invisible; acceptable because valuation is already daily-snapshot based. Documented, not mitigated.
- [Divide-by-zero on a zero/negative peak] → Guard the drawdown ratio so a non-positive running peak contributes no drawdown.
- [Extra read work per KPI call] → One additional pass over already-fetched snapshots plus one closed-positions query; negligible and on an interactive, non-hot path.
