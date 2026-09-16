## 1. Reconciliation core (paper-trading service)

- [x] 1.1 Add `TERMINAL_ORDER_STATUSES = {FILLED, CANCELLED, REJECTED}` to `paper_trading/constants.py` (import `OrderStatus` from broker models).
- [x] 1.2 Add `list_nonterminal_trades(db, session_id) -> list[PaperTrade]` to `paper_trading/service.py` (filter `order_id IS NOT NULL` and `order_status NOT IN` terminal set).
- [x] 1.3 Add `adjust_ledger_cost_basis(db, *, session_id, ticker, trade_qty, delta_price)` to `paper_trading/service.py`: load the open `SessionPosition`; if present and `position_qty > 0`, set `avg_cost = avg_cost + (delta_price * trade_qty) / position_qty`; no-op if the position is closed. Commit/refresh.
- [x] 1.4 Add a `ReconcileResult` dataclass/return shape (counts: `trades_seen`, `trades_reconciled`, `trades_filled`, `trades_basis_corrected`) — plain object the router maps to a schema.
- [x] 1.5 Add `reconcile_session_orders(db, broker, session_id) -> ReconcileResult` to `paper_trading/service.py`: raise `SessionNotFoundError` for unknown id; for each non-terminal trade, capture `old_price = filled_price if not None else price`, call `broker.get_order(order_id)` (skip on `None`, guarded by try/except so one failure continues the batch), update `order_status`/`filled_price`/`filled_at`, and when `side == BUY` and `order.filled_price` is not None and differs from `old_price`, call `adjust_ledger_cost_basis` with `delta_price = order.filled_price - old_price`.

## 2. Endpoints & schemas

- [x] 2.1 Add `PaperTradeReconcileRead` (counts) and `AIDailyReconcileResponse` (`sessions_reconciled`, `trades_reconciled`) to `api/schemas.py`; the per-session response also carries the refreshed trades (reuse `PaperTradeRead`).
- [x] 2.2 `api/routers/paper_trading.py`: add `POST /sessions/{id}/reconcile` injecting `BrokerDep`; call `reconcile_session_orders`, then return counts + refreshed `get_session_trades`; map `SessionNotFoundError` → 404.
- [x] 2.3 `api/routers/ai_portfolio.py`: add `POST /reconcile-daily` guarded by `require_valid_cron_token`, injecting `BrokerDep` + `DbSession`; list all sessions (paper_trading service), call `reconcile_session_orders` per session inside try/except (one failure does not stop the run), aggregate into `AIDailyReconcileResponse`.

## 3. Backend tests

- [x] 3.1 Service: a non-terminal buy whose stub order later reports filled updates `order_status`/`filled_price`/`filled_at`; a terminal trade and a trade without `order_id` are left untouched; a `get_order` returning `None`/raising skips that trade and continues.
- [x] 3.2 Service (ledger): reconciling a buy whose actual fill differs from the recorded price adjusts the open `SessionPosition.avg_cost`; an equal fill price leaves it unchanged; a closed position is skipped.
- [x] 3.3 Service: `reconcile_session_orders` raises `SessionNotFoundError` for an unknown id.
- [x] 3.4 API: `POST /sessions/{id}/reconcile` returns counts + refreshed trades (200), 404 for unknown session.
- [x] 3.5 API: `POST /ai-portfolio/reconcile-daily` reconciles across sessions with a valid token (200 + aggregate), 403 without a valid `X-Cron-Token`, and one failing session does not abort the run.

## 4. Frontend

- [x] 4.1 `types/api.ts`: add a `PaperTradeReconcileResult` type (counts + `trades: PaperTrade[]`); confirm `PaperTrade.order_status` covers the terminal values.
- [x] 4.2 `api/paperTrading.ts`: add `isTerminalOrderStatus(status)` (`filled`/`cancelled`/`rejected`) and `useSessionOrderSync(sessionId)` — a `useQuery` POSTing `/sessions/{id}/reconcile` with `refetchInterval` returning `POLL_INTERVAL_MS` while any returned trade is non-terminal and `false` once all are terminal; on settle, invalidate the session trades, positions, and value-snapshot query keys.
- [x] 4.3 `pages/paper-trading/PaperTradingSessionPage.tsx`: call `useSessionOrderSync(id)` near the top so the page reconciles on mount and polls until terminal; `TradesPanel`/positions/chart refresh via the invalidations.
- [x] 4.4 Co-located Vitest: `useSessionOrderSync` polls while a trade is non-terminal and stops when all terminal; opening the session page issues the reconcile call; the trades list reflects reconciled statuses.

## 5. Verification

- [x] 5.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 5.2 Frontend: `npm run typecheck && npx vitest run && npm run build`.
- [x] 5.3 `openspec validate add-order-status-reconciliation --strict`.
