"""SQLAlchemy 2.0 ORM models for the strategy-bot subsystem.

Schema is owned by Alembic; these models are the source of truth for autogenerate.
Three tables, deliberately independent of the paper-trading tables (no cross-domain
foreign keys):

- ``bot_sessions`` — one row per bot, binding a strategy to a single universe
  asset, carrying its capital, risk parameters, and **inline position state**
  (``position_qty``/``position_avg_price``/``position_opened_at``, null when flat).
  v1 holds at most one position per session, so columns beat a positions table.
- ``bot_trades`` — individual fills recorded by the engine (buys and sells).
- ``bot_value_snapshots`` — one daily portfolio-value snapshot per session per day
  (the equity curve), unique on ``(bot_session_id, snapshot_date)``.

``bot_sessions`` references ``assets`` by ``asset_id`` (the shared-universe read
seam); the child tables FK to the session and cascade-delete with it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Date,
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
from cadence.strategy_bots.constants import BotSessionStatus


def _enum_column(enum: type[Enum]) -> SQLEnum:
    """A non-native enum column storing the member ``value`` (like the assets domain)."""
    return SQLEnum(
        enum,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
    )


class BotSession(Base):
    """A strategy bot: one deterministic strategy applied to one universe asset.

    Long-only, equities-only, single all-in whole-share position in v1. The
    position state lives inline (``position_qty``/``position_avg_price``/
    ``position_opened_at``, all null when flat) rather than in a separate table,
    because a session holds at most one position. ``peak_value`` tracks the running
    high-water mark used by the drawdown kill-switch. ``allocated_capital`` is the
    running total of contributed capital (equal to ``initial_capital`` in v1, which
    has no capital-increase path), surfaced so the dashboard contribution math
    matches the AI sessions.
    """

    __tablename__ = "bot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # The registered strategy driving this bot (a StrategyKey value). Stored as
    # free text (like paper_trading.strategy_key) so a new strategy is additive;
    # creation rejects an unregistered key.
    strategy_key: Mapped[str] = mapped_column(Text, nullable=False)
    # The single universe asset this bot trades (the shared-universe read seam).
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    # The asset's canonical ticker, frozen at creation for display and ordering
    # without re-reading the asset row.
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional human-facing label; falls back to "<strategy> · <ticker>" in reads.
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # One of cadence.strategy_bots.constants.BotSessionStatus values.
    status: Mapped[str] = mapped_column(
        _enum_column(BotSessionStatus),
        nullable=False,
        server_default=BotSessionStatus.ACTIVE.value,
    )
    # The benchmark index this bot is compared against (a Benchmark catalog id).
    benchmark: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="SP500"
    )
    initial_capital: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="100000"
    )
    allocated_capital: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="100000"
    )
    # Strategy parameters (e.g. fast/slow SMA windows), validated against the
    # strategy's params schema at creation and read back verbatim by the runner.
    strategy_params: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    # Optional risk exits, as fractions of the position's average cost. Null = off.
    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Drawdown kill-switch threshold (fraction of peak value). Non-null: always on.
    drawdown_stop_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.25"
    )
    # Cash buffer reserved before all-in sizing (fraction of allocated capital).
    cash_buffer_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.02"
    )
    # Running high-water mark of total value, for the drawdown kill-switch. Seeded
    # to the initial capital at creation; updated by the tick/snapshot path.
    peak_value: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="100000"
    )
    # Inline single-position state. All null when the session is flat.
    position_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Running totals maintained by the engine as trades are recorded.
    total_trades: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    realised_pnl: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    total_fees: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
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
    last_tick_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    trades: Mapped[list[BotTrade]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    value_snapshots: Mapped[list[BotValueSnapshot]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_flat(self) -> bool:
        """Whether the session currently holds no position."""
        return not self.position_qty


class BotTrade(Base):
    """A single fill recorded by the bot engine (a buy entry or a sell exit)."""

    __tablename__ = "bot_trades"
    __table_args__ = (
        Index("idx_bot_trades_session", "bot_session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    bot_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Trade direction, from the broker vocabulary (buy/sell).
    side: Mapped[str] = mapped_column(_enum_column(OrderSide), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0"
    )
    # The strategy/engine reason that produced this fill (e.g. "sma_up_cross",
    # "stop_loss", "drawdown_kill_switch"), for the trade ledger.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Broker order status of the fill (defaults to a completed 'filled').
    status: Mapped[str] = mapped_column(
        _enum_column(OrderStatus),
        nullable=False,
        server_default=OrderStatus.FILLED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[BotSession] = relationship(back_populates="trades")


class BotValueSnapshot(Base):
    """A daily portfolio-value snapshot for a bot session — one row per day.

    Captured by the daily bot-snapshot cron: marks the session's holding (if any)
    to market and records its ``total_value`` (equity), plus the cumulative
    ``realised_pnl`` and live ``unrealised_pnl`` at capture time. Unique on
    ``(bot_session_id, snapshot_date)`` so re-running the cron on the same day
    updates that day's row rather than duplicating it.
    """

    __tablename__ = "bot_value_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "bot_session_id",
            "snapshot_date",
            name="uq_bot_value_snapshots_session_date",
        ),
        Index(
            "idx_bot_value_snapshots_session_date",
            "bot_session_id",
            "snapshot_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    bot_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    realised_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    unrealised_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[BotSession] = relationship(back_populates="value_snapshots")
