"""Integration tests for the paper-trading service against Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cadence.api.schemas import SessionValueSnapshotRead
from cadence.broker.models import OrderSide, OrderStatus, Quote
from cadence.paper_trading import service
from cadence.paper_trading.constants import RunStatus, ScheduleMode, SessionStatus
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    SessionNotFoundError,
)
from cadence.portfolios import service as portfolios_service
from cadence.portfolios.models import Portfolio


def _portfolio(db_session: Session) -> Portfolio:
    return portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL", "MSFT"]
    )


def test_create_session_defaults(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
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
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
    with pytest.raises(DuplicateSessionError):
        service.create_session(
            db_session, portfolio_id=portfolio.id, strategy_key="momentum"
        )


def test_get_and_not_found(db_session: Session) -> None:
    import uuid

    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s"
    )
    assert service.get_session(db_session, sess.id).id == sess.id
    with pytest.raises(SessionNotFoundError):
        service.get_session(db_session, uuid.uuid4())


def test_record_trade_derives_notional(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s"
    )
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


def test_record_run(db_session: Session) -> None:
    portfolio = _portfolio(db_session)
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="s"
    )
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
        db_session, portfolio_id=portfolio.id, strategy_key="s"
    )
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
        db_session, portfolio_id=portfolio.id, strategy_key="s"
    )
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
        db_session, portfolio_id=portfolio.id, strategy_key="a"
    )
    stopped = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b"
    )
    service.update_session_status(db_session, stopped.id, SessionStatus.STOPPED)

    active_ids = [
        s.id for s in service.list_sessions(db_session, status=SessionStatus.ACTIVE)
    ]
    assert active.id in active_ids
    assert stopped.id not in active_ids


# --------------------------------------------------------------------------- #
# Open-position ledger
# --------------------------------------------------------------------------- #


def _ledger_session(db_session: Session) -> object:
    portfolio = _portfolio(db_session)
    return service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="ledger"
    )


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
        db_session, portfolio_id=portfolio.id, strategy_key="a"
    )
    b = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="b"
    )
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
        allocated_capital=100_000.0,
    )


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
