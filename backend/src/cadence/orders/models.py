"""The ``broker_orders`` journal table."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Float, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base


class OrderOwnerKind(StrEnum):
    """Who an order belongs to (and whose ledger books its fill)."""

    BOT = "bot"
    AI_SESSION = "ai_session"
    ADMIN = "admin"


class JournalState(StrEnum):
    """Lifecycle of a journal row.

    ``INTENT`` is written before the broker call; ``SUBMITTED`` once the broker call
    returned (or raised — the broker may still have received it); ``RESOLVED`` once its
    fills are booked or it is known to have none; ``REFUSED`` when the long-only guard
    stopped it before submission; ``NOT_SUBMITTED`` when the broker never received it.
    """

    INTENT = "intent"
    SUBMITTED = "submitted"
    RESOLVED = "resolved"
    REFUSED = "refused"
    NOT_SUBMITTED = "not_submitted"


#: States that still need reconciliation.
UNRESOLVED_STATES = (JournalState.INTENT.value, JournalState.SUBMITTED.value)


class BrokerOrder(Base):
    """One order Cadence decided to send to the broker, recorded before sending."""

    __tablename__ = "broker_orders"
    __table_args__ = (
        Index("idx_broker_orders_owner", "owner_kind", "owner_id"),
        Index(
            "idx_broker_orders_unresolved",
            "lease_until",
            postgresql_where=text("state IN ('intent', 'submitted') AND booked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    client_order_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    owner_kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Cadence ticker (ledger spelling) and the symbol actually sent to the broker.
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    broker_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    # Why the order was sent (e.g. "entry", "session_stopped", "ai_rebalance_sell").
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    # Owner-specific data needed to book the fill later (e.g. a bot's asset id).
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    filled_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Until then the owner is still working on the order; reconciliation keeps out.
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
