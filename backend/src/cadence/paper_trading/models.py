"""SQLAlchemy 2.0 ORM models for paper trading.

Schema is owned by Alembic; these models are the source of truth for
autogenerate. Ported from trading-bot's ``paper_trading_repository`` as four
tables:

- ``paper_trading_sessions`` — one row per ``(portfolio, strategy)`` pair
  (enforced UNIQUE), configuring how the strategy is paper-traded.
- ``paper_trades`` — individual fills recorded during a session.
- ``session_runs`` — a log entry per scan/rebalance run of a session.
- ``closed_positions`` — realized-P&L records when a position is closed.

Sessions FK to ``portfolios``; the three child tables FK to the session and
cascade-delete with it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cadence.broker.models import OrderSide, OrderStatus
from cadence.database import Base
from cadence.paper_trading.constants import RunStatus, ScheduleMode, SessionStatus


def _enum_column(enum: type[Enum]) -> SQLEnum:
    """A non-native enum column storing the member ``value`` (like the assets domain)."""
    return SQLEnum(
        enum,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
    )


class PaperTradingSession(Base):
    """A paper-trading session: one strategy applied to one portfolio.

    Unique on ``(portfolio_id, strategy_key)`` so a portfolio can only run a
    given strategy once. ``session_metadata`` maps to the ``metadata`` column
    (the attribute is renamed to avoid clashing with SQLAlchemy's reserved
    ``Base.metadata``). Running totals (``total_trades``/``total_pnl``) and
    ``last_run_at`` are maintained as runs are recorded.
    """

    __tablename__ = "paper_trading_sessions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "strategy_key",
            name="uq_paper_trading_sessions_portfolio_strategy",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    strategy_key: Mapped[str] = mapped_column(Text, nullable=False)
    # One of cadence.paper_trading.constants.SessionStatus values.
    status: Mapped[str] = mapped_column(
        _enum_column(SessionStatus),
        nullable=False,
        server_default=SessionStatus.ACTIVE.value,
    )
    allocated_capital: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="100000"
    )
    max_allocation_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="1.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_pnl: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    # Column name kept as ``metadata`` (faithful to trading-bot); the Python
    # attribute is renamed because ``metadata`` is reserved on the declarative base.
    session_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    # One of cadence.paper_trading.constants.ScheduleMode values.
    schedule_mode: Mapped[str] = mapped_column(
        _enum_column(ScheduleMode),
        nullable=False,
        server_default=ScheduleMode.SCHEDULED.value,
    )

    trades: Mapped[list[PaperTrade]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    runs: Mapped[list[SessionRun]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    closed_positions: Mapped[list[ClosedPosition]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PaperTrade(Base):
    """A single fill recorded during a paper-trading session."""

    __tablename__ = "paper_trades"
    __table_args__ = (
        Index("idx_paper_trades_session", "session_id"),
        Index("idx_paper_trades_executed", "executed_at"),
        Index("idx_paper_trades_ai_event", "ai_portfolio_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The AI build/rebalance event that produced this trade, when applicable.
    # Nullable: non-AI strategies and legacy rows leave it empty. SET NULL on
    # event deletion so a trade outlives the audit row that referenced it.
    ai_portfolio_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_portfolio_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    # Trade direction, from the broker vocabulary (buy/sell).
    side: Mapped[str] = mapped_column(_enum_column(OrderSide), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    notional: Mapped[float] = mapped_column(Float, nullable=False)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Broker order status of the fill (defaults to a completed 'filled').
    order_status: Mapped[str] = mapped_column(
        _enum_column(OrderStatus),
        nullable=False,
        server_default=OrderStatus.FILLED.value,
    )
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped[PaperTradingSession] = relationship(back_populates="trades")


class SessionRun(Base):
    """A record of a single scan/rebalance run of a session."""

    __tablename__ = "session_runs"
    __table_args__ = (Index("idx_session_runs_session", "session_id", "run_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    signals_scanned: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    signals_actionable: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    orders_executed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    orders_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    details: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # One of cadence.paper_trading.constants.RunStatus values.
    status: Mapped[str] = mapped_column(
        _enum_column(RunStatus),
        nullable=False,
        server_default=RunStatus.SUCCESS.value,
    )
    # Free-form label for what triggered the run (e.g. 'scheduled', 'manual').
    run_trigger: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="scheduled"
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[PaperTradingSession] = relationship(back_populates="runs")


class ClosedPosition(Base):
    """A closed position with realized P&L and holding period."""

    __tablename__ = "closed_positions"
    __table_args__ = (
        Index("idx_closed_positions_session", "session_id", "exit_date"),
        Index("idx_closed_positions_ai_event", "ai_portfolio_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The AI rebalance event that closed this position, when applicable. Nullable
    # (non-AI strategies / legacy rows leave it empty); SET NULL on event delete.
    ai_portfolio_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_portfolio_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    # Signed: positive for a long, negative for a short.
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    exit_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)

    session: Mapped[PaperTradingSession] = relationship(
        back_populates="closed_positions"
    )
