"""Integration tests for the paper-trading service against Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cadence.api.schemas import SessionValueSnapshotRead
from cadence.broker.models import (
    AssetClass,
    Order,
    OrderSide,
    OrderStatus,
    Quote,
)
from cadence.config import settings
from cadence.paper_trading import service
from cadence.paper_trading.constants import (
    SHARPE_MIN_RETURNS,
    RunStatus,
    ScheduleMode,
    SessionStatus,
)
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    SessionNotArchivableError,
    SessionNotFoundError,
)
from cadence.paper_trading.models import SessionValueSnapshot
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.models import Portfolio


def _portfolio(db_session: Session) -> Portfolio:
    return portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL", "MSFT"]
    )


def test_create_session_defaults(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1)
    assert sess.id is not None
    assert sess.portfolio_id == portfolio.id
    assert sess.status == SessionStatus.ACTIVE.value
    assert sess.allocated_capital == 100000.0
    assert sess.schedule_mode == ScheduleMode.SCHEDULED.value
    assert sess.total_trades == 0
    assert sess.total_pnl == 0.0


def test_duplicate_portfolio_strategy_raises(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1)
    with pytest.raises(DuplicateSessionError):
        service.create_session(
            db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1)


def test_get_and_not_found(db_session: Session) -> None:
    import uuid

    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    assert service.get_session(db_session, sess.id).id == sess.id
    with pytest.raises(SessionNotFoundError):
        service.get_session(db_session, uuid.uuid4())


def test_record_trade_derives_notional(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    trade = service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=25.0,
        signal_type="entry",
        order_status=OrderStatus.FILLED,
    )
    assert trade.notional == 250.0
    assert trade.side == OrderSide.BUY.value
    assert trade.order_status == OrderStatus.FILLED.value
    assert service.count_session_trades(db_session, sess.id) == 1


def test_record_trade_charges_transaction_fee(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    # A fresh session starts fee-free.
    assert sess.total_fees == pytest.approx(0.0)
    for _ in range(2):
        service.record_trade(
            db_session,
            session_id=sess.id,
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            price=10.0,
            signal_type="entry",
        )
    # Every recorded trade charges the flat per-trade cost onto the session.
    refreshed = service.get_session(db_session, sess.id)
    assert refreshed.total_fees == pytest.approx(2 * settings.TRANSACTION_COST_USD)


def test_record_run(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    run = service.record_session_run(
        db_session,
        session_id=sess.id,
        signals_scanned=5,
        signals_actionable=2,
        orders_executed=1,
        orders_skipped=1,
        details=[{"ticker": "AAPL", "action": "buy"}],
        status=RunStatus.SUCCESS,
        run_trigger="manual",
        duration_ms=123,
    )
    assert run.signals_scanned == 5
    assert run.status == RunStatus.SUCCESS.value
    assert run.run_trigger == "manual"
    assert run.details == [{"ticker": "AAPL", "action": "buy"}]
    assert service.count_session_runs(db_session, sess.id) == 1


def test_record_closed_position_computes_pnl(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    entry = datetime(2026, 1, 1, tzinfo=UTC)
    exit_ = entry + timedelta(days=10)
    pos = service.record_closed_position(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        quantity=10,
        entry_price=100.0,
        exit_price=110.0,
        entry_date=entry,
        exit_date=exit_,
    )
    assert pos.realized_pnl == pytest.approx(100.0)
    assert pos.return_pct == pytest.approx(0.1)
    assert pos.holding_days == 10
    assert service.count_closed_positions(db_session, sess.id) == 1


def test_update_last_run_and_status(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s", rebalance_prompt_version=1)
    updated = service.update_session_last_run(
        db_session, sess.id, trades_delta=3, pnl_delta=42.5
    )
    assert updated.total_trades == 3
    assert updated.total_pnl == pytest.approx(42.5)
    assert updated.last_run_at is not None

    paused = service.update_session_status(
        db_session, sess.id, SessionStatus.PAUSED
    )
    assert paused.status == SessionStatus.PAUSED.value


def test_list_sessions_filter_by_status(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    active = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1)
    stopped = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b", rebalance_prompt_version=1)
    service.update_session_status(db_session, stopped.id, SessionStatus.STOPPED)

    active_ids = [
        s.id for s in service.list_sessions(db_session, status=SessionStatus.ACTIVE)
    ]
    assert active.id in active_ids
    assert stopped.id not in active_ids


# --------------------------------------------------------------------------- #
# Archiving
# --------------------------------------------------------------------------- #


def _stopped_session(db_session: Session, strategy_key: str = "s") -> object:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key=strategy_key, rebalance_prompt_version=1)
    return service.update_session_status(
        db_session, sess.id, SessionStatus.STOPPED
    )


def test_archive_stopped_session_sets_timestamp(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    archived = service.archive_session(db_session, sess.id)
    assert archived.archived_at is not None
    # Archiving does not change status.
    assert archived.status == SessionStatus.STOPPED.value


def test_archive_rejects_active_or_paused(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    active = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1)
    with pytest.raises(SessionNotArchivableError):
        service.archive_session(db_session, active.id)

    service.update_session_status(db_session, active.id, SessionStatus.PAUSED)
    with pytest.raises(SessionNotArchivableError):
        service.archive_session(db_session, active.id)


def test_unarchive_clears_timestamp(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    service.archive_session(db_session, sess.id)
    restored = service.unarchive_session(db_session, sess.id)
    assert restored.archived_at is None


def test_default_list_hides_archived(db_session: Session) -> None:
    sess = _stopped_session(db_session)
    service.archive_session(db_session, sess.id)

    visible_ids = [s.id for s in service.list_sessions(db_session)]
    assert sess.id not in visible_ids
    assert service.count_sessions(db_session) == 0

    with_archived = [
        s.id for s in service.list_sessions(db_session, include_archived=True)
    ]
    assert sess.id in with_archived
    assert service.count_sessions(db_session, include_archived=True) == 1


def test_archive_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.archive_session(db_session, uuid.uuid4())
    with pytest.raises(SessionNotFoundError):
        service.unarchive_session(db_session, uuid.uuid4())


# --------------------------------------------------------------------------- #
# Open-position ledger
# --------------------------------------------------------------------------- #


def _ledger_session(db_session: Session) -> object:
    portfolio = _portfolio(db_session)
    return service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="ledger", rebalance_prompt_version=1)


def test_apply_fill_to_ledger_opens_and_averages_up(db_session: Session) -> None:
    sess = _ledger_session(db_session)

    # First buy opens the entry at the fill price.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(10)
    assert entry.avg_cost == pytest.approx(100.0)

    # Second buy increases quantity and re-computes the weighted-average cost:
    # (10*100 + 10*120) / 20 = 110.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=120.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(20)
    assert entry.avg_cost == pytest.approx(110.0)


def test_apply_fill_to_ledger_partial_sell_then_full_exit(db_session: Session) -> None:
    sess = _ledger_session(db_session)
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )

    # Partial sell reduces quantity, leaving the weighted-average cost unchanged.
    entry = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.SELL,
        shares=4,
        price=130.0,
    )
    assert entry is not None
    assert entry.quantity == pytest.approx(6)
    assert entry.avg_cost == pytest.approx(100.0)

    # Full exit removes the row entirely.
    removed = service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.SELL,
        shares=6,
        price=130.0,
    )
    assert removed is None
    assert service.get_open_position(db_session, sess.id, "AAPL") is None


def test_list_open_positions_scoped_to_session(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    a = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="a", rebalance_prompt_version=1)
    b = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b", rebalance_prompt_version=1)
    service.apply_fill_to_ledger(
        db_session, session_id=a.id, ticker="AAPL", side=OrderSide.BUY,
        shares=5, price=50.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=a.id, ticker="MSFT", side=OrderSide.BUY,
        shares=3, price=40.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=b.id, ticker="AAPL", side=OrderSide.BUY,
        shares=8, price=90.0,
    )

    a_positions = service.list_open_positions(db_session, a.id)
    assert {p.ticker for p in a_positions} == {"AAPL", "MSFT"}
    # The same ticker in another session tracks its own independent quantity/cost.
    a_aapl = service.get_open_position(db_session, a.id, "AAPL")
    b_aapl = service.get_open_position(db_session, b.id, "AAPL")
    assert a_aapl is not None and a_aapl.quantity == pytest.approx(5)
    assert b_aapl is not None and b_aapl.quantity == pytest.approx(8)


def test_get_position_entry_basis_is_pre_sell(db_session: Session) -> None:
    sess = _ledger_session(db_session)
    opened = service.apply_fill_to_ledger(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        shares=10, price=100.0,
    )
    service.apply_fill_to_ledger(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        shares=10, price=120.0,
    )
    assert opened is not None

    basis = service.get_position_entry_basis(db_session, sess.id, "AAPL")
    assert basis is not None
    avg_cost, opened_at = basis
    # Basis reflects the weighted-average cost (110) and the original opened date.
    assert avg_cost == pytest.approx(110.0)
    assert opened_at == opened.opened_at

    assert service.get_position_entry_basis(db_session, sess.id, "NONE") is None


# --------------------------------------------------------------------------- #
# Order-status reconciliation
# --------------------------------------------------------------------------- #


class _OrderBroker:
    """Broker double that returns pre-seeded orders keyed by order id.

    ``orders`` maps order_id -> ``Order`` (the broker's current view). An order_id
    mapped to ``None`` simulates an order the broker no longer knows about; an
    order_id listed in ``raises`` makes ``get_order`` blow up for that id (the
    transient-failure path).
    """

    def __init__(
        self,
        orders: dict[str, Order | None],
        *,
        raises: set[str] | None = None,
    ) -> None:
        self._orders = orders
        self._raises = raises or set()

    def get_order(self, order_id: str) -> Order | None:
        if order_id in self._raises:
            raise RuntimeError("get_order boom")
        return self._orders.get(order_id)


def _filled_order(
    ticker: str,
    side: OrderSide,
    qty: float,
    price: float,
    *,
    order_id: str,
) -> Order:
    return Order(
        symbol=ticker,
        side=side,
        quantity=qty,
        asset_class=AssetClass.EQUITY,
        order_id=order_id,
        status=OrderStatus.FILLED,
        filled_quantity=qty,
        filled_price=price,
        filled_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def test_reconcile_updates_nonterminal_buy_to_filled(db_session: Session) -> None:
    sess = _ai_session(db_session)
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=100.0,
        signal_type="entry",
        order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 100.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_seen == 1
    assert result.trades_reconciled == 1
    assert result.trades_filled == 1

    (trade,) = service.get_session_trades(db_session, sess.id)
    assert trade.order_status == OrderStatus.FILLED.value
    assert trade.filled_price == pytest.approx(100.0)
    assert trade.filled_at is not None


def test_reconcile_leaves_terminal_and_orderless_trades_untouched(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # Already terminal — never re-queried.
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=1, price=10.0, signal_type="entry", order_id="done",
        order_status=OrderStatus.FILLED,
    )
    # No broker order id — nothing to reconcile against.
    service.record_trade(
        db_session, session_id=sess.id, ticker="MSFT", side=OrderSide.BUY,
        quantity=1, price=20.0, signal_type="entry",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"done": _filled_order("AAPL", OrderSide.BUY, 1, 999.0, order_id="done")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_seen == 0
    assert result.trades_reconciled == 0


def test_reconcile_skips_missing_or_failing_order_and_continues(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=1, price=10.0, signal_type="entry", order_id="gone",
        order_status=OrderStatus.SUBMITTED,
    )
    service.record_trade(
        db_session, session_id=sess.id, ticker="MSFT", side=OrderSide.BUY,
        quantity=1, price=20.0, signal_type="entry", order_id="boom",
        order_status=OrderStatus.SUBMITTED,
    )
    service.record_trade(
        db_session, session_id=sess.id, ticker="NVDA", side=OrderSide.BUY,
        quantity=1, price=30.0, signal_type="entry", order_id="ok",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {
            "gone": None,  # broker no longer knows this order
            "ok": _filled_order("NVDA", OrderSide.BUY, 1, 30.0, order_id="ok"),
        },
        raises={"boom"},
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    # All three seen; only the healthy one reconciled — the batch never aborts.
    assert result.trades_seen == 3
    assert result.trades_reconciled == 1
    assert result.trades_filled == 1


def test_reconcile_corrects_ledger_cost_basis_on_price_delta(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # Open the ledger at the estimated fill price, then record the pending trade.
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    # Broker reports the actual fill at 105 -> +5/share correction over 10 shares.
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 105.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_basis_corrected == 1

    entry = service.get_open_position(db_session, sess.id, "AAPL")
    assert entry is not None
    # avg_cost = 100 + (5 * 10) / 10 = 105.
    assert entry.avg_cost == pytest.approx(105.0)


def test_reconcile_equal_fill_price_is_noop_for_ledger(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 100.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    assert result.trades_basis_corrected == 0
    entry = service.get_open_position(db_session, sess.id, "AAPL")
    assert entry is not None
    assert entry.avg_cost == pytest.approx(100.0)


def test_reconcile_price_delta_on_closed_position_skips_ledger(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    # A pending buy whose position never opened (or was already fully sold).
    service.record_trade(
        db_session, session_id=sess.id, ticker="AAPL", side=OrderSide.BUY,
        quantity=10, price=100.0, signal_type="entry", order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    broker = _OrderBroker(
        {"o1": _filled_order("AAPL", OrderSide.BUY, 10, 105.0, order_id="o1")}
    )
    result = service.reconcile_session_orders(db_session, broker, sess.id)
    # Trade still reconciled, but no open ledger entry to correct.
    assert result.trades_reconciled == 1
    assert result.trades_basis_corrected == 0
    assert service.get_open_position(db_session, sess.id, "AAPL") is None


def test_reconcile_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.reconcile_session_orders(db_session, _OrderBroker({}), uuid.uuid4())


# --------------------------------------------------------------------------- #
# Portfolio-value snapshots
# --------------------------------------------------------------------------- #


class _QuoteBroker:
    """Minimal broker double that prices the tickers it is configured with.

    ``prices`` maps ticker -> price. A ticker mapped to ``None`` yields a quote
    with no usable price (exercises the avg-cost fallback); a ticker absent from
    the map is omitted from the result entirely (a missing symbol). ``raises``
    makes ``get_quotes`` blow up wholesale (the total quote-fetch failure path).
    """

    def __init__(
        self, prices: dict[str, float | None], *, raises: bool = False
    ) -> None:
        self._prices = prices
        self._raises = raises

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        if self._raises:
            raise RuntimeError("quote boom")
        out: dict[str, Quote] = {}
        for sym in symbols:
            if sym not in self._prices:
                continue
            price = self._prices[sym]
            if price is None:
                out[sym] = Quote(symbol=sym)
            else:
                out[sym] = Quote(symbol=sym, bid=price, ask=price, last=price)
        return out


def _ai_session(db_session: Session) -> object:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL", "MSFT"]
    )
    return service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        allocated_capital=100_000.0, rebalance_prompt_version=1)


def _buy(db_session: Session, session_id: object, ticker: str, qty: float, price: float) -> None:
    service.apply_fill_to_ledger(
        db_session,
        session_id=session_id,
        ticker=ticker,
        side=OrderSide.BUY,
        shares=qty,
        price=price,
    )


def test_compute_value_all_cash(db_session: Session) -> None:
    sess = _ai_session(db_session)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    # No holdings -> equity is exactly the seed capital, all in cash.
    assert valuation.total_value == pytest.approx(100_000.0)
    assert valuation.positions_value == pytest.approx(0.0)
    assert valuation.cash_value == pytest.approx(100_000.0)
    assert valuation.positions == []


def test_compute_value_marked_up_holding(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # cost basis 1000
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # +20/share on 10 shares = +200 unrealized.
    assert valuation.positions_value == pytest.approx(1200.0)
    assert valuation.total_value == pytest.approx(100_200.0)
    assert valuation.cash_value == pytest.approx(99_000.0)
    (pos,) = valuation.positions
    assert pos["ticker"] == "AAPL"
    assert pos["market_value"] == pytest.approx(1200.0)
    assert pos["unrealized_pnl"] == pytest.approx(200.0)
    assert pos["return_pct"] == pytest.approx(0.2)


def test_compute_value_marked_down_holding(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 80.0})
    )
    assert valuation.positions_value == pytest.approx(800.0)
    assert valuation.total_value == pytest.approx(99_800.0)
    (pos,) = valuation.positions
    assert pos["unrealized_pnl"] == pytest.approx(-200.0)
    assert pos["return_pct"] == pytest.approx(-0.2)


def test_compute_value_quote_failure_isolated_to_one_ticker(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # priced 120 -> +200
    _buy(db_session, sess.id, "MSFT", 5, 50.0)  # no usable quote -> avg cost
    valuation = service.compute_session_value(
        db_session,
        session_id=sess.id,
        broker=_QuoteBroker({"AAPL": 120.0, "MSFT": None}),
    )
    by_ticker = {p["ticker"]: p for p in valuation.positions}
    # AAPL marked up as normal; MSFT falls back to its avg cost (flat, no P&L).
    assert by_ticker["AAPL"]["unrealized_pnl"] == pytest.approx(200.0)
    assert by_ticker["MSFT"]["price"] == pytest.approx(50.0)
    assert by_ticker["MSFT"]["unrealized_pnl"] == pytest.approx(0.0)
    # AAPL 1200 + MSFT 250 = 1450 of positions value; +200 total P&L.
    assert valuation.positions_value == pytest.approx(1450.0)
    assert valuation.total_value == pytest.approx(100_200.0)


def test_compute_value_total_quote_failure_falls_back_to_cost(
    db_session: Session,
) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    valuation = service.compute_session_value(
        db_session, session_id=sess.id, broker=_QuoteBroker({}, raises=True)
    )
    # A wholesale get_quotes failure values every holding at avg cost (flat).
    assert valuation.positions_value == pytest.approx(1000.0)
    assert valuation.total_value == pytest.approx(100_000.0)


def test_record_snapshot_is_idempotent_per_day(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    broker = _QuoteBroker({"AAPL": 100.0})
    day = date(2026, 1, 5)

    first = service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=day, broker=broker
    )
    second = service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=day, broker=broker
    )
    # Two runs for the same day update one row (same id), never insert twice.
    assert first.id == second.id
    assert len(service.list_value_snapshots(db_session, session_id=sess.id)) == 1
    # No prior snapshot -> baseline is the allocated capital (flat -> zero P&L).
    assert second.daily_pnl == pytest.approx(0.0)
    assert second.daily_pnl_pct == pytest.approx(0.0)


def test_record_snapshot_daily_pnl_uses_prior(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)

    # Day 1: flat at cost -> total == allocated, baseline == allocated.
    day1 = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 5),
        broker=_QuoteBroker({"AAPL": 100.0}),
    )
    assert day1.total_value == pytest.approx(100_000.0)

    # Day 2: marked up to 120 -> +200 vs the prior day's total_value.
    day2 = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 6),
        broker=_QuoteBroker({"AAPL": 120.0}),
    )
    assert day2.total_value == pytest.approx(100_200.0)
    assert day2.daily_pnl == pytest.approx(200.0)
    assert day2.daily_pnl_pct == pytest.approx(200.0 / 100_000.0)


def test_list_value_snapshots_ascending(db_session: Session) -> None:
    sess = _ai_session(db_session)
    broker = _QuoteBroker({})
    for day in (date(2026, 1, 6), date(2026, 1, 4), date(2026, 1, 5)):
        service.record_value_snapshot(
            db_session, session_id=sess.id, as_of=day, broker=broker
        )
    dates = [
        s.snapshot_date
        for s in service.list_value_snapshots(db_session, session_id=sess.id)
    ]
    assert dates == [date(2026, 1, 4), date(2026, 1, 5), date(2026, 1, 6)]


def test_snapshot_row_validates_into_read_schema(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)
    row = service.record_value_snapshot(
        db_session,
        session_id=sess.id,
        as_of=date(2026, 1, 5),
        broker=_QuoteBroker({"AAPL": 120.0}),
    )
    read = SessionValueSnapshotRead.model_validate(row)
    assert read.snapshot_date == date(2026, 1, 5)
    assert read.total_value == pytest.approx(100_200.0)
    assert read.positions[0]["ticker"] == "AAPL"


def test_compute_value_surfaces_unrealized_pnl(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200
    _buy(db_session, sess.id, "MSFT", 5, 50.0)  # -10/share -> -50
    valuation = service.compute_session_value(
        db_session,
        session_id=sess.id,
        broker=_QuoteBroker({"AAPL": 120.0, "MSFT": 40.0}),
    )
    # Top-level unrealised P&L equals the sum of the per-position marks.
    per_position = sum(p["unrealized_pnl"] for p in valuation.positions)
    assert valuation.unrealized_pnl == pytest.approx(150.0)
    assert valuation.unrealized_pnl == pytest.approx(per_position)


# --------------------------------------------------------------------------- #
# Sharpe ratio (pure helper)
# --------------------------------------------------------------------------- #


def test_sharpe_ratio_known_series() -> None:
    returns = [0.01] * 10 + [0.02] * 10  # 20 observations, non-zero variance
    assert service.sharpe_ratio(returns) == pytest.approx(46.417669, abs=1e-4)


def test_sharpe_ratio_none_below_minimum() -> None:
    returns = [0.01, -0.01] * ((SHARPE_MIN_RETURNS - 1) // 2)
    assert len(returns) < SHARPE_MIN_RETURNS
    assert service.sharpe_ratio(returns) is None


def test_sharpe_ratio_none_when_flat() -> None:
    # Enough observations but zero standard deviation -> no signal, no divide-by-zero.
    assert service.sharpe_ratio([0.01] * SHARPE_MIN_RETURNS) is None


def test_sharpe_ratio_excess_over_risk_free() -> None:
    returns = [0.01] * 10 + [0.02] * 10
    # A positive risk-free rate lowers the numerator, hence the ratio.
    assert service.sharpe_ratio(returns, risk_free=0.001) < service.sharpe_ratio(
        returns
    )


# --------------------------------------------------------------------------- #
# Session KPIs
# --------------------------------------------------------------------------- #


def _add_snapshot(
    db_session: Session, session_id: object, day: date, daily_pnl_pct: float
) -> None:
    """Insert a minimal value snapshot carrying a daily return for Sharpe tests."""
    db_session.add(
        SessionValueSnapshot(
            session_id=session_id,
            snapshot_date=day,
            total_value=0.0,
            cash_value=0.0,
            positions_value=0.0,
            daily_pnl=0.0,
            daily_pnl_pct=daily_pnl_pct,
            positions=[],
        )
    )
    db_session.commit()


def test_session_kpis_live_figures_and_total_return(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200 unrealised
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    assert kpis.current_value == pytest.approx(100_200.0)
    assert kpis.realised_pnl == pytest.approx(0.0)
    assert kpis.unrealised_pnl == pytest.approx(200.0)
    # Total return, absolute and fractional, vs the 100k allocated capital.
    assert kpis.total_return == pytest.approx(200.0)
    assert kpis.total_return == pytest.approx(kpis.realised_pnl + kpis.unrealised_pnl)
    assert kpis.total_return_pct == pytest.approx(200.0 / 100_000.0)
    # No snapshots yet -> Sharpe not yet available.
    assert kpis.sharpe_ratio is None


def test_session_kpis_net_of_fees_and_gross_realised(db_session: Session) -> None:
    sess = _ai_session(db_session)
    _buy(db_session, sess.id, "AAPL", 10, 100.0)  # +20/share -> +200 unrealised
    # Two executed trades accrue transaction fees on the session.
    for _ in range(2):
        service.record_trade(
            db_session,
            session_id=sess.id,
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=1,
            price=10.0,
            signal_type="entry",
        )
    fees = 2 * settings.TRANSACTION_COST_USD
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({"AAPL": 120.0})
    )
    # Current value is net of fees; total_fees is surfaced.
    assert kpis.total_fees == pytest.approx(fees)
    assert kpis.current_value == pytest.approx(100_200.0 - fees)
    assert kpis.total_return == pytest.approx(200.0 - fees)
    # Realised P&L stays gross (fees are tracked separately, not folded in).
    assert kpis.realised_pnl == pytest.approx(0.0)


def test_session_kpis_sharpe_none_until_enough_history(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    for i in range(SHARPE_MIN_RETURNS - 1):  # one short of the minimum
        _add_snapshot(db_session, sess.id, base + timedelta(days=i), 0.01 + 0.001 * i)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert kpis.sharpe_ratio is None


def test_session_kpis_sharpe_from_snapshot_series(db_session: Session) -> None:
    sess = _ai_session(db_session)
    base = date(2026, 1, 1)
    returns = [0.01] * 10 + [0.02] * 10
    for i, ret in enumerate(returns):
        _add_snapshot(db_session, sess.id, base + timedelta(days=i), ret)
    kpis = service.session_kpis(
        db_session, session_id=sess.id, broker=_QuoteBroker({})
    )
    assert kpis.sharpe_ratio == pytest.approx(46.417669, abs=1e-4)


def test_session_kpis_unknown_session_raises(db_session: Session) -> None:
    import uuid

    with pytest.raises(SessionNotFoundError):
        service.session_kpis(
            db_session, session_id=uuid.uuid4(), broker=_QuoteBroker({})
        )
