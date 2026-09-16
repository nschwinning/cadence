## Why

A paper-trading order's status, fill price, and fill time are captured exactly
once — from the broker's response at submission — and never updated again. An
order submitted while the market is closed (or that fills gradually) is recorded
as `pending`/`submitted` and stays that way forever, so the UI shows a
non-terminal status that never resolves and the open-position ledger's cost basis
is stuck at the pre-trade quote instead of the real fill price. Users need order
state to track toward its terminal value and the recorded cost basis to reflect
what actually filled.

## What Changes

- Add a **reconciliation pass** that, for a session's non-terminal trades that
  carry a broker order id, re-fetches the order from the broker
  (`broker.get_order(order_id)`) and updates the stored `order_status`,
  `filled_price`, and `filled_at`.
- When a reconciled fill price differs from the price recorded at submission,
  **correct the open-position ledger cost basis** (`avg_cost`) for that ticker so
  it reflects the actual fill.
- Trigger reconciliation **two ways**:
  - **On demand / server-side per session**: reconciling a single session's open
    orders (invoked when its detail page is opened and while polling).
  - **Via cron**: a new `X-Cron-Token`-guarded endpoint that reconciles the open
    orders of all sessions on a schedule, so orders resolve even when no one is
    viewing them.
- **Frontend**: the session detail page syncs a session's orders on mount and
  polls while any order is non-terminal, stopping once all orders are terminal.

## Capabilities

### Modified Capabilities
- `ai-paper-trading`: add order-reconciliation behavior — reconcile a session's
  non-terminal trades against the broker until terminal, correct the ledger cost
  basis from actual fills, and a cron entry point that reconciles all sessions.
- `app-shell`: the session detail view syncs order state on open and polls while
  orders are non-terminal.

## Impact

- Backend: `paper_trading/service.py` (new reconcile function, trade listing by
  non-terminal status, ledger basis correction), `ai_portfolio/service.py` or a
  reconciliation entry point that iterates sessions, `broker` Protocol (`get_order`
  already exists on `AlpacaBroker`/`StubBroker`), `api/routers/paper_trading.py`
  (per-session reconcile + cron endpoint), `api/schemas.py` (reconcile result
  shape). No schema migration — `paper_trades` already has `order_status`,
  `filled_price`, `filled_at`.
- Frontend: `api/paperTrading.ts` (reconcile mutation + poll-until-terminal),
  `pages/paper-trading/PaperTradingSessionPage.tsx` (trigger on mount, poll),
  `types/api.ts`.
- Ops: a new cron endpoint to register alongside the existing daily-rebalancing /
  snapshot crons.
