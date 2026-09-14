"""Integration tests for the paper-trading service against Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from cadence.broker.models import OrderSide, OrderStatus
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
