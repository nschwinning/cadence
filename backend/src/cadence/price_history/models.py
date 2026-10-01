"""SQLAlchemy 2.0 ORM for stored daily close prices per asset.

Schema is owned by Alembic; this model is the source of truth for autogenerate.
One table ``price_history`` holds a single daily close per asset and trading
date (unique on ``(asset_id, date)``), the time series the Dashboard reads to
compute per-asset market return over a range. Each asset keeps only the dates on
which it has a close, so assets on different trading calendars (24/7 crypto vs
market-hours equities) coexist without fabricated points.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base


class PriceHistory(Base):
    """One stored daily close for an asset on a trading date."""

    __tablename__ = "price_history"
    __table_args__ = (
        # Unique per asset+date so re-ingesting a date updates rather than
        # duplicates it; the backing index also serves the (asset_id, date)
        # range lookups used to resolve a range's start close.
        UniqueConstraint("asset_id", "date", name="uq_price_history_asset_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
