## Context

See proposal.md - Why. Session KPIs are computed in `paper_trading/service.py::session_kpis`, which already fetches the session's ordered daily value snapshots (`list_value_snapshots`) and reads `total_fees` off the session ORM row. The KPI values flow through the `SessionKpis` dataclass → `PaperTradingSessionKpisRead` schema (with an explicit field-by-field mapping in `get_session_kpis`) → the frontend `PaperTradingSessionKpis` type → the `KpiRow` component on `PaperTradingSessionPage.tsx`, which renders shared `StatTile`s. The KPI grid currently has two groups: **Performance** (9 tiles, `lg:grid-cols-4`) and **Risk & trade quality** (6 tiles, `lg:grid-cols-3`).

## Goals / Non-Goals

**Goals:**
- Add a `daily_avg_transaction_cost` KPI computed as `total_fees ÷ snapshot_count`, `null` when there are no snapshots.
- Reflow the Performance group to a two-row × five-tile grid (its 9 tiles + the new one = 10) and reduce the shared tile/font size.

**Non-Goals:**
- No new persistence: both inputs (`total_fees`, daily snapshots) already exist — no DB column, no migration.
- Not changing the Risk & trade quality group's tile *set* (it keeps its 6 tiles); it only inherits the smaller shared tile styling.
- No change to how `total_fees` is accrued or how snapshots are recorded.

## Decisions

- **Basis = snapshot-day count (confirmed with user).** `daily_avg_transaction_cost = total_fees / len(snapshots)` using the snapshots already loaded in `session_kpis`. Alternatives considered and rejected: per-calendar-day since start (penalises weekends/gaps and diverges from the snapshot series the other KPIs use) and per-active-trading-day (requires deriving trading days, no existing source). Using the snapshot count keeps it consistent with Sharpe/drawdown, which already consume the same series.
- **`null` when no snapshots**, mirroring the Sharpe "insufficient history" convention, so a brand-new session never divides by zero and the UI shows a "not yet available" state. Field type is `float | None` in the dataclass/schema and `number | null` in the TS type.
- **Tile placement**: the new tile goes in the Performance group immediately after "Transaction fees", formatted with `formatCurrency`, with a hint clarifying the per-snapshot-day basis and a fallback label when `null`.
- **Layout**: Performance grid becomes `lg:grid-cols-5` (two rows of five on wide viewports), keeping `grid-cols-1 sm:grid-cols-2` at smaller breakpoints. `StatTile` padding shrinks (e.g. `p-6` → `p-4`), the value font drops (e.g. `text-3xl` → `text-2xl`), and the gap tightens — applied in the shared component so both groups read as more compact.

## Risks / Trade-offs

- [Shrinking shared `StatTile` affects every consumer of the component, including the dashboard] → Audit other `StatTile` call sites before changing it; if the dashboard tiles should keep their current size, pass the size via a prop/variant rather than hard-changing the base. Default assumption: a modest reduction is acceptable everywhere, but this is verified during apply.
- [Interpreting "2 rows with 5 tiles" as the Performance group (9+1=10), not the whole 16-tile area] → The arithmetic only fits the Performance group; dropping the hard-won risk/trade tiles would be a surprising loss. Recorded here so the user can redirect at review if they meant the entire KPI area.
- [Fees accrue continuously but snapshots are daily] → The metric is explicitly "per snapshot day", documented in the tile hint, so the denominator's meaning is clear to the viewer.
