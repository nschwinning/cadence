## Why

The Dashboard's top point-in-time band shows a single "Total value" tile that occupies a quarter of the page width, leaving the band looking sparse. Operators want a fuller live snapshot of how the selected portfolios are doing right now — not just what they are worth, but how much they have earned, and whether they are beating the market — without changing the range selector.

## What Changes

- The point-in-time "Portfolio value" band expands from one live tile to **four** live/point-in-time tiles that span the full page width, all range-independent (they do **not** change with the range selector):
  1. **Total value** (existing) — Σ current value across the selected sessions.
  2. **Total return %** (new) — since-inception money-weighted simple return = (Σ current value − Σ contributed capital) ÷ Σ contributed capital; sign-distinguished.
  3. **Lifetime P&L $** (new) — since-inception dollar gain = Σ current value − Σ contributed capital; sign-distinguished.
  4. **Return vs benchmark** (new) — since-inception excess return % = portfolio total return − benchmark buy-and-hold return, where each session is compared against its **own** benchmark; sign-distinguished (outperformance vs underperformance).
- "Contributed capital" is the sum of each session's existing `contributions[].amount` (opening capital plus every later capital increase) already returned by the overview.
- The three new figures are derived **client-side** by aggregating already-fetched per-session fields, so toggling the session selection re-aggregates with no refetch (preserving the existing dashboard behaviour).
- The overview gains one new **per-session** field, `benchmark_value` (nullable), carrying the current USD value of a since-inception **contribution-aware** buy-and-hold of that session's contributions in its own benchmark — the same basis as the dashboard's existing combined-equity benchmark overlay (`rebased_benchmark_value`), so the benchmark leg is money-weighted to match the money-weighted portfolio return — so the client can aggregate the excess-return figure across whatever sessions are selected.
- When any selected session has an unpriceable benchmark (`benchmark_value` null), the **Return vs benchmark** tile shows a clear "not yet available" state rather than reporting a misleading excess.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: the "Dashboard aggregate performance tiles" requirement — the point-in-time value band now presents four range-independent live tiles (current value, since-inception total return %, since-inception lifetime P&L $, and since-inception excess return vs benchmark %), spanning the full page width, with the three new figures sign-distinguished and the vs-benchmark tile showing a "not yet available" state when a selected session's benchmark is unpriceable.
- `dashboard`: the "Per-session performance data for the overview" requirement — the overview additionally returns a per-session since-inception contribution-aware benchmark buy-and-hold current value (`benchmark_value`, nullable) computed on the same basis as the dashboard's combined-equity benchmark overlay, enabling the client to aggregate an excess-return figure across the selected sessions.

## Impact

- **Backend:** `dashboard/service.py` (`_session_performance` + the `SessionPerformance` dataclass) computes and carries `benchmark_value`, reusing the session's contributions + its benchmark full-history series via the existing `paper_trading/benchmark.py` buy-and-hold logic (no range floor). `api/schemas.py` `DashboardSessionPerformance` gains `benchmark_value: float | None`. No new endpoint, no new migration, no schema table change.
- **Frontend:** `types/api.ts` `DashboardSessionPerformance` gains `benchmark_value`. `pages/dashboard/aggregate.ts` gains pure helpers for aggregate contributed capital, lifetime P&L, since-inception total return, aggregate benchmark value, and excess-vs-benchmark (with null handling). `pages/dashboard/HeroTiles.tsx` `ValueTiles` renders the four-tile full-width band (reusing `StatTile` + `signClass`).
- **Out of scope:** no change to the range-scoped performance tiles, the combined equity chart + its benchmark overlay, the leaderboard, universe, automation, or recent-activity; no change to the 30s live auto-refresh cadence; no new benchmark return math; no change to the session-detail KPIs/TWR; the range selector still governs only the range-scoped region.
