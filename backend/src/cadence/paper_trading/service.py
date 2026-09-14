"""Paper-trading service/repository: business logic and data access.

Routers stay thin and delegate here. All DB access for the paper-trading domain
lives in this module. These functions port trading-bot's repository methods to
service functions operating on a SQLAlchemy :class:`Session`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence.broker.models import OrderSide, OrderStatus
from cadence.paper_trading.constants import RunStatus, ScheduleMode, SessionStatus
from cadence.paper_trading.errors import (
    DuplicateSessionError,
    SessionNotFoundError,
)
from cadence.paper_trading.models import (
    ClosedPosition,
    PaperTrade,
    PaperTradingSession,
    SessionRun,
)

# Default seed capital for a new session (mirrors trading-bot).
DEFAULT_ALLOCATED_CAPITAL = 100000.0


def create_session(
    session: Session,
    *,
    portfolio_id: uuid.UUID,
    strategy_key: str,
    allocated_capital: float = DEFAULT_ALLOCATED_CAPITAL,
    max_allocation_pct: float = 1.0,
    schedule_mode: ScheduleMode = ScheduleMode.SCHEDULED,
) -> PaperTradingSession:
    """Create a paper-trading session for a ``(portfolio, strategy)`` pair.

    Raises:
        DuplicateSessionError: if a session already exists for the same
            ``(portfolio_id, strategy_key)`` (the UNIQUE constraint).
    """
    row = PaperTradingSession(
        portfolio_id=portfolio_id,
        strategy_key=strategy_key,
        status=SessionStatus.ACTIVE.value,
        allocated_capital=allocated_capital,
        max_allocation_pct=max_allocation_pct,
        schedule_mode=schedule_mode.value,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateSessionError(
            f"A session already exists for portfolio {portfolio_id} "
            f"and strategy {strategy_key!r}"
        ) from exc
    session.refresh(row)
    return row


def get_session(session: Session, session_id: uuid.UUID) -> PaperTradingSession:
    """Return a session by id or raise :class:`SessionNotFoundError`."""
    row = session.get(PaperTradingSession, session_id)
    if row is None:
        raise SessionNotFoundError(f"Paper trading session {session_id} not found")
    return row


def list_sessions(
    session: Session,
    *,
    status: SessionStatus | None = None,
    limit: int = 50,
) -> list[PaperTradingSession]:
    """List sessions, most recently updated first, optionally filtered by status."""
    stmt = select(PaperTradingSession).order_by(
        PaperTradingSession.updated_at.desc(), PaperTradingSession.id.desc()
    )
    if status is not None:
        stmt = stmt.where(PaperTradingSession.status == status.value)
    return list(session.execute(stmt.limit(limit)).scalars())


def count_sessions(
    session: Session, *, status: SessionStatus | None = None
) -> int:
    """Count sessions, optionally filtered by status."""
    stmt = select(func.count()).select_from(PaperTradingSession)
    if status is not None:
        stmt = stmt.where(PaperTradingSession.status == status.value)
    return session.execute(stmt).scalar_one()


def update_session_status(
    session: Session,
    session_id: uuid.UUID,
    status: SessionStatus,
) -> PaperTradingSession:
    """Update a session's status. Raises if the session does not exist."""
    row = get_session(session, session_id)
    row.status = status.value
    session.commit()
    session.refresh(row)
    return row


def update_session_last_run(
    session: Session,
    session_id: uuid.UUID,
    *,
    trades_delta: int = 0,
    pnl_delta: float = 0.0,
) -> PaperTradingSession:
    """Stamp ``last_run_at`` and add to the running trade count / P&L totals."""
    row = get_session(session, session_id)
    row.last_run_at = datetime.now(tz=UTC)
    row.total_trades = row.total_trades + trades_delta
    row.total_pnl = row.total_pnl + pnl_delta
    session.commit()
    session.refresh(row)
    return row


def record_trade(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    side: OrderSide,
    quantity: float,
    price: float,
    signal_type: str,
    order_id: str | None = None,
    order_status: OrderStatus = OrderStatus.FILLED,
    filled_price: float | None = None,
    filled_at: datetime | None = None,
) -> PaperTrade:
    """Record a paper trade (fill). ``notional`` is derived as ``quantity * price``."""
    trade = PaperTrade(
        session_id=session_id,
        ticker=ticker,
        side=side.value,
        quantity=quantity,
        price=price,
        notional=quantity * price,
        signal_type=signal_type,
        order_id=order_id,
        order_status=order_status.value,
        filled_price=filled_price,
        filled_at=filled_at,
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)
    return trade


def get_session_trades(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[PaperTrade]:
    """Return a session's trades, most recent first."""
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.session_id == session_id)
        .order_by(PaperTrade.executed_at.desc(), PaperTrade.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def count_session_trades(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's trades."""
    stmt = (
        select(func.count())
        .select_from(PaperTrade)
        .where(PaperTrade.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


def record_session_run(
    session: Session,
    *,
    session_id: uuid.UUID,
    signals_scanned: int = 0,
    signals_actionable: int = 0,
    orders_executed: int = 0,
    orders_skipped: int = 0,
    details: list[dict[str, Any]] | None = None,
    status: RunStatus = RunStatus.SUCCESS,
    run_trigger: str = "scheduled",
    duration_ms: int | None = None,
) -> SessionRun:
    """Record a session run (a single scan/rebalance)."""
    run = SessionRun(
        session_id=session_id,
        signals_scanned=signals_scanned,
        signals_actionable=signals_actionable,
        orders_executed=orders_executed,
        orders_skipped=orders_skipped,
        details=details,
        status=status.value,
        run_trigger=run_trigger,
        duration_ms=duration_ms,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_session_runs(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[SessionRun]:
    """Return a session's run history, most recent first."""
    stmt = (
        select(SessionRun)
        .where(SessionRun.session_id == session_id)
        .order_by(SessionRun.run_at.desc(), SessionRun.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def count_session_runs(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's runs."""
    stmt = (
        select(func.count())
        .select_from(SessionRun)
        .where(SessionRun.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()


def record_closed_position(
    session: Session,
    *,
    session_id: uuid.UUID,
    ticker: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    entry_date: datetime,
    exit_date: datetime,
) -> ClosedPosition:
    """Record a closed position, deriving realized P&L, return, and holding days.

    ``quantity`` is signed: positive for a long, negative for a short. Return is
    derived over the absolute cost basis so the sign stays correct for both.
    """
    realized_pnl = (exit_price - entry_price) * quantity
    cost_basis = entry_price * abs(quantity)
    return_pct = realized_pnl / cost_basis if cost_basis > 0 else 0.0
    holding_days = (exit_date - entry_date).days

    position = ClosedPosition(
        session_id=session_id,
        ticker=ticker,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_date=entry_date,
        exit_date=exit_date,
        realized_pnl=realized_pnl,
        return_pct=return_pct,
        holding_days=holding_days,
    )
    session.add(position)
    session.commit()
    session.refresh(position)
    return position


def get_closed_positions(
    session: Session,
    session_id: uuid.UUID,
    *,
    limit: int = 100,
) -> list[ClosedPosition]:
    """Return a session's closed positions, most recently exited first."""
    stmt = (
        select(ClosedPosition)
        .where(ClosedPosition.session_id == session_id)
        .order_by(ClosedPosition.exit_date.desc(), ClosedPosition.id.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def count_closed_positions(session: Session, session_id: uuid.UUID) -> int:
    """Count a session's closed positions."""
    stmt = (
        select(func.count())
        .select_from(ClosedPosition)
        .where(ClosedPosition.session_id == session_id)
    )
    return session.execute(stmt).scalar_one()
