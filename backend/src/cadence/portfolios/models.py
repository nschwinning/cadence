"""SQLAlchemy 2.0 ORM model for portfolios.

Schema is owned by Alembic; this model is the source of truth for autogenerate.
Ported from trading-bot's ``portfolios`` table: a named basket of tickers with a
source, an optional risk profile, and a per-name allocation cap. ``stocks`` is a
Postgres text array; a CHECK constraint enforces at least one ticker.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base
from cadence.portfolios.constants import PortfolioSource, RiskProfile


class Portfolio(Base):
    """A named basket of tickers with provenance and an optional risk profile.

    ``source`` and ``risk_profile`` are each stored as their enum's string value
    (non-native enum) to keep migrations simple; ``risk_profile`` is nullable.
    ``stocks`` holds normalized (upper-cased, de-duplicated) tickers and is never
    empty, enforced by the ``stocks_not_empty`` CHECK constraint.
    """

    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint("array_length(stocks, 1) >= 1", name="stocks_not_empty"),
        Index("idx_portfolios_created_at", "created_at"),
        Index("idx_portfolios_source", "source"),
        Index("idx_portfolios_source_run", "source_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stocks: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    max_allocation_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="1.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # One of cadence.portfolios.constants.PortfolioSource values.
    source: Mapped[str] = mapped_column(
        SQLEnum(
            PortfolioSource,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    # One of cadence.portfolios.constants.RiskProfile values, or NULL.
    risk_profile: Mapped[str | None] = mapped_column(
        SQLEnum(
            RiskProfile,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    # Free-form provenance link (e.g. a recommendation run id) for AI/recommended
    # portfolios; NULL for manually created ones.
    source_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
