## Why

A paper-trading session's asset scope (stocks / crypto / both) is frozen at AI-build time and buried inside `session_metadata["asset_types"]` — it is neither shown on the session details page nor changeable afterwards. Operators cannot see what a session is scoped to, and cannot narrow a session that is drifting into unwanted asset classes (or widen one to let the AI use crypto) without rebuilding from scratch.

## What Changes

- **Surface the scope** on the paper-trading session read model and show it as a fact tile on the session details page.
- **Make the scope editable** from the session details page via a new scope switcher, backed by a new `PUT /paper-trading/sessions/{id}/scope` endpoint that mutates `session_metadata["asset_types"]`. Future builds/rebalances, the weekend crypto cron, and weekend snapshot gating already re-read this value, so they honor the new scope automatically.
- **Liquidate out-of-scope holdings when narrowing.** When the new scope excludes the asset class of any currently-held position, the change immediately sells those now-out-of-scope positions, charging the standard per-trade transaction cost and refreshing the session's recorded value. Widening the scope (or any change that excludes nothing held) liquidates nothing.
- Changing a session to the **same** scope is a no-op (no liquidation), and still returns the session.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ai-paper-trading`: the session read model exposes the session's asset scope; a new operation changes a session's asset scope, immediately liquidating any now-out-of-scope holdings (with transaction costs and a refreshed valuation) when the scope narrows, and doing nothing to holdings when it widens or is unchanged.
- `app-shell`: the session details page shows the session's scope and provides an in-page control to change it, with pending/error feedback.

## Impact

- **Backend:** `api/schemas.py` (new `asset_types` field on `PaperTradingSessionRead`; new scope-change request model), `api/routers/paper_trading.py` (new `PUT .../scope` endpoint, broker dependency, error mapping), `paper_trading/service.py` (new scope-change service function performing validation, metadata mutation, and narrowing liquidation), `paper_trading/errors.py` (invalid-scope error if needed). Reuses `assets/category.py` (`AssetScope`, `scope_categories`), the existing sell/`record_trade`/`total_fees` machinery, and `compute_session_value`. No migration (scope stays in JSON metadata).
- **Frontend:** `types/api.ts` (scope on `PaperTradingSession`), `api/paperTrading.ts` (raw fn + mutation hook), `pages/paper-trading/PaperTradingSessionPage.tsx` (read tile + scope switcher).
- **Behavioral:** weekend crypto-daily rebalance gating and weekend snapshot gating follow the new scope; the `max_asset_class_pct` guardrail can become vacuous when narrowing to a single class (documented, no action). No secrets involved.
