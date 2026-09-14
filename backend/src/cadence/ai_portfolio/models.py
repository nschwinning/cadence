"""SQLAlchemy 2.0 ORM model for AI portfolio events.

Schema is owned by Alembic; this model is the source of truth for autogenerate.
Ported from trading-bot's ``ai_portfolio_events`` table (an audit trail of build
and rebalance jobs) and adapted to Cadence conventions: a UUID primary key,
``Mapped[]`` columns, non-native enums stored by value, and nullable foreign keys
to the portfolios and paper-trading sessions a job creates or acts on.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.database import Base


def _enum_column(enum: type[Enum]) -> SQLEnum:
    """A non-native enum column storing the member ``value`` (like the assets domain)."""
    return SQLEnum(
        enum,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
    )


class AIPortfolioEvent(Base):
    """Audit-trail row for a single AI portfolio build or rebalance job.

    ``session_id`` and ``portfolio_id`` are nullable: a *build* job creates both
    only after the agent succeeds, so they are stamped mid-job; a delete of either
    parent nulls the link (``SET NULL``) rather than losing the audit row.
    ``request_payload`` captures the job's inputs, ``result_payload`` the agent's
    structured output, and ``actions_taken`` the per-ticker trade results.
    """

    __tablename__ = "ai_portfolio_events"
    __table_args__ = (
        Index("idx_ai_portfolio_events_session", "session_id", "created_at"),
        Index("idx_ai_portfolio_events_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("paper_trading_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="SET NULL"),
        nullable=True,
    )
    # One of cadence.ai_portfolio.constants.EventType values.
    event_type: Mapped[str] = mapped_column(_enum_column(EventType), nullable=False)
    # One of cadence.ai_portfolio.constants.EventStatus values.
    status: Mapped[str] = mapped_column(
        _enum_column(EventStatus),
        nullable=False,
        server_default=EventStatus.QUEUED.value,
    )
    # Inputs the job was queued with (tickers, capital, flags, ...).
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # The agent's structured output (model_dump), when the run reached the agent.
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Per-ticker trade results produced by the executor.
    actions_taken: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
