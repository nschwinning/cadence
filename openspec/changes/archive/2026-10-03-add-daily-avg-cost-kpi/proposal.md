## Why

The paper-trading session detail page reports cumulative transaction fees but gives no sense of the *ongoing drag* those fees impose per trading day. A daily-average transaction cost makes fee burn comparable across sessions of different ages and surfaces whether a strategy trades too often for its returns. The KPI grid has also grown to 15 tiles at a large tile/font size; the Performance block in particular is crowded and reads better as a compact two-row grid.

## What Changes

- Add a new session KPI **daily average transaction cost** = cumulative `total_fees` ÷ number of recorded daily value snapshots. It is `null` when the session has no snapshots yet (same "not enough history" convention the Sharpe KPI already uses).
- Expose the new KPI end-to-end: backend `SessionKpis` dataclass, the `PaperTradingSessionKpisRead` schema + its explicit router mapping, and the frontend `PaperTradingSessionKpis` type.
- Render it as a new tile in the session-detail **Performance** group, placed next to "Transaction fees".
- Redesign the KPI tiles: the Performance group becomes a **2-row × 5-tile** grid (its 9 existing tiles + the new one = 10), and the shared `StatTile` gets smaller padding, value, and label font sizes so the whole KPI area (both groups) is more compact.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: add the daily-average-transaction-cost KPI to the session performance KPIs requirement (computation from `total_fees` and the snapshot-day count, `null` without snapshots, exposed on the KPIs read model).
- `app-shell`: redesign the session-detail KPI tile layout — Performance group as a 2×5 grid with the new tile, and a smaller shared tile/font size.

## Impact

- **Backend**: `paper_trading/service.py` (`SessionKpis` dataclass + `session_kpis` computation), `api/schemas.py` (`PaperTradingSessionKpisRead`), `api/routers/paper_trading.py` (explicit field mapping in `get_session_kpis`). No DB change, no migration (fees and snapshots already persisted).
- **Frontend**: `types/api.ts` (`PaperTradingSessionKpis`), `pages/paper-trading/PaperTradingSessionPage.tsx` (`KpiRow` grid + new tile), `components/dashboard/StatTile.tsx` (smaller padding/font).
- **Tests**: backend KPI service + API tests; frontend `PaperTradingSessionPage.test.tsx` tile assertions/fixtures.
