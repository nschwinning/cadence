## Context

A `PaperTrade` row's `order_status`, `filled_price`, and `filled_at` are written
once, in `paper_trading.service.record_trade`, from the broker `Order` returned at
submission (`ai_portfolio.service._record_trades`, service.py:970-1010). Nothing ever
re-reads the order: `Broker.get_order(order_id)` exists
(`alpaca.py:272-280`, `stub.py:223-225`) but is never called. So an order submitted
while the market is closed stays `submitted`/`pending` forever, and the open-position
ledger (`SessionPosition.avg_cost`, built by `apply_fill_to_ledger`, service.py:403)
keeps the pre-trade quote as its cost basis (it was applied with
`price = tr.filled_price or tr.price or 0.0`, so a pending trade used the quote).

The broker Protocol, the `paper_trades` columns, and the ledger table already exist —
this change adds the reconciliation logic, two entry points (per-session + cron), and
a frontend sync/poll. No Alembic migration is needed.

The cron convention lives in `api/routers/ai_portfolio.py`:
`require_valid_cron_token` (:72-89) reads `X-Cron-Token`, compares against
`settings.REBALANCE_CRON_TOKEN` with `hmac.compare_digest`, 403 on mismatch; existing
crons `rebalance-daily` (:213) and `snapshot-daily` (:256) take
`_token: Annotated[None, Depends(require_valid_cron_token)]` as the last param.
Frontend polling convention: `aiPortfolio.ts` `useBuildStatus` (:205-218) uses
`refetchInterval: (query) => isTerminalEventStatus(status) ? false : POLL_INTERVAL_MS`.

## Goals / Non-Goals

**Goals:**
- Reconcile a session's non-terminal trades against the broker until terminal,
  updating `order_status` / `filled_price` / `filled_at`.
- Correct the open-position ledger `avg_cost` when a reconciled buy fills at a price
  different from the estimate recorded at submission.
- Two triggers: a per-session reconcile (frontend calls on mount + poll) and an
  `X-Cron-Token`-guarded endpoint reconciling all sessions.
- Robust to broker failure: a bad order/broker error skips that trade and continues.

**Non-Goals:**
- No retroactive correction of realized P&L on already-closed positions (sells): a
  sell's trade fields are reconciled, but the `ClosedPosition.realized_pnl` derived at
  sell time is not re-derived. The "ledger basis" corrected here is the open-position
  cost basis only.
- No new order-status vocabulary, no migration, no partial-fill accounting beyond
  treating `partially_filled` as non-terminal (keep re-querying).
- No websockets/push — reconciliation is pull (page poll + cron).

## Decisions

- **Terminal set.** Add `TERMINAL_ORDER_STATUSES = {FILLED, CANCELLED, REJECTED}` to
  `paper_trading/constants.py`. `submitted`, `pending`, `partially_filled` are
  non-terminal and keep being re-queried. (Mirrors `Order.is_complete`,
  models.py:107.)

- **Service reconcile function.** Add
  `reconcile_session_orders(db, broker, session_id) -> ReconcileResult` to
  `paper_trading/service.py`. It loads the session (raise `SessionNotFoundError` if
  unknown), lists that session's trades whose `order_id is not None` and
  `order_status` not terminal, and for each calls `broker.get_order(order_id)`:
  - `None` (unknown/broker error handled inside `get_order`) → skip, count as
    unreconciled, continue.
  - otherwise capture the trade's **effective old price**
    (`filled_price if filled_price is not None else price`) *before* mutating, then set
    `order_status = _map(order.status)`, `filled_price = order.filled_price` (when not
    None), `filled_at = order.filled_at` (when not None).
  - **Ledger correction (buys only):** if `side == BUY`, `order.filled_price` is not
    None, and it differs from the effective old price, adjust the ticker's open
    `SessionPosition` cost basis via a new helper
    `adjust_ledger_cost_basis(db, session_id, ticker, trade_qty, delta_price)` where
    `delta_price = order.filled_price - old_price`, computing
    `new_avg = old_avg + (delta_price * trade_qty) / position_qty`. If the position is
    no longer open, skip (nothing to correct).
  Return counts (sessions is implicit here: trades_reconciled, trades_filled, etc.).
  Wrap broker calls defensively so one raising trade can't abort the batch.

- **Where the broker comes from.** `reconcile_session_orders` takes `broker: Broker`
  explicitly (matching the service's explicit-dependency style); the router injects
  `BrokerDep`.

- **Per-session endpoint.** `POST /api/v1/paper-trading/sessions/{id}/reconcile` in
  `api/routers/paper_trading.py`, injecting `BrokerDep`. Returns a `ReconcileResult`
  read model (trades_reconciled / trades_filled counts) plus the refreshed trade list
  so the client can render without a second round-trip; 404 on unknown session. This
  matches the action-style POST convention used by close/rebalance.

- **Cron endpoint.** `POST /api/v1/ai-portfolio/reconcile-daily` in
  `api/routers/ai_portfolio.py`, alongside the other crons, guarded by
  `require_valid_cron_token`. It lists all sessions (via paper_trading service) and
  calls `reconcile_session_orders` for each inside a try/except so one failure doesn't
  stop the run; returns an aggregate summary (`sessions_reconciled`,
  `trades_reconciled`). Runs synchronously in the request (like `snapshot-daily`); no
  ThreadPoolExecutor needed. A new `AIDailyReconcileResponse` schema.

- **Trade listing.** Add `list_nonterminal_trades(db, session_id) -> list[PaperTrade]`
  to `paper_trading/service.py` (filter `order_id IS NOT NULL` and `order_status NOT
  IN terminal`), used by `reconcile_session_orders`. Keep `get_session_trades`
  unchanged.

- **Frontend.** In `api/paperTrading.ts` add `isTerminalOrderStatus(status)` (checks
  `filled`/`cancelled`/`rejected`) and a `useSessionOrderSync(sessionId)` hook: a
  `useQuery` whose `queryFn` POSTs `/reconcile`, with
  `refetchInterval: (q) => q.state.data?.trades.every(t =>
  isTerminalOrderStatus(t.order_status)) ? false : POLL_INTERVAL_MS`, and on settle
  invalidates the session-value + positions query keys so the chart/positions refresh.
  `PaperTradingSessionPage.tsx` calls `useSessionOrderSync(id)` near the top (mount +
  poll); `TradesPanel` continues to render `useSessionTrades`, which the reconcile
  invalidation refreshes. Add `ReconcileResult` + reuse `PaperTrade` in `types/api.ts`.

## Risks / Trade-offs

- **Partial sell before reconcile.** If a ticker's position was reduced between the
  buy and its reconcile, `position_qty < trade_qty`, so the `avg_cost` correction is
  approximate (it prices the delta over the remaining shares). Acceptable: reconcile
  normally runs before any exit, and the cron runs frequently; the alternative
  (per-lot basis tracking) is out of scope. Documented as a non-goal above.
- **POST used as a poll.** `useSessionOrderSync` issues a mutating POST on an interval.
  It is idempotent (terminal trades are never re-queried; a matching fill price leaves
  the ledger untouched), so repeated calls converge and stop once terminal.
- **Broker rate / latency.** Reconcile fans out one `get_order` per non-terminal
  trade. Sessions have few open orders at a time; the cron iterates sessions
  sequentially. If this grows, batch by broker order list — not needed now.
- **Test DB.** No schema change, so no migration risk; `StubBroker.get_order` returns
  the stored order, and `StubBroker` fills market orders immediately — tests seed a
  non-terminal order to exercise the transition.
