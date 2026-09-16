"""SQLAlchemy 2.0 ORM model for the assets universe.

Schema is owned by Alembic; this model is the source of truth for autogenerate.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cadence.assets.category import AssetCategory
from cadence.assets.sector import Sector
from cadence.database import Base


class Asset(Base):
    """An asset in Cadence's curated universe with an eligibility snapshot.

    Monetary metrics are stored in EUR (converted from the native ``currency``
    at add time). ``category`` and ``sector`` are each stored as their enum's
    string value (non-native enum) to keep migrations simple; ``sector`` is
    nullable ("no sector" is a valid state). ``criteria_results``
    holds the per-criterion evaluation as a JSONB list of
    ``{name, passed, value, threshold}`` objects.
    """

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # The brokerage's (Alpaca) canonical symbol for this asset, captured and
    # verified at add time (e.g. ``BRK.B`` for yfinance ``BRK-B``, ``BTC/USD``
    # for ``BTC-USD``). Nullable so any pre-existing rows remain valid; every new
    # asset populates it (add is rejected unless Alpaca confirms tradability).
    alpaca_symbol: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(
        SQLEnum(AssetCategory, native_enum=False, values_callable=lambda enum: [
            member.value for member in enum
        ]),
        nullable=False,
    )
    # Economic sector, stored as the provider's stable slug (non-native enum,
    # like ``category``). Nullable: reliably populated only for equities, so
    # "no sector" (crypto, most ETFs/funds) is a first-class state.
    sector: Mapped[str | None] = mapped_column(
        SQLEnum(Sector, native_enum=False, values_callable=lambda enum: [
            member.value for member in enum
        ]),
        nullable=True,
    )
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    # Native trading currency (ISO code).
    currency: Mapped[str] = mapped_column(String, nullable=False)
    # Stable company-profile fields, captured from the provider at add time and
    # refreshed when the asset is re-added. All nullable: any field the provider
    # omits (and every asset added before this change) is stored as NULL. Unlike
    # the time-varying volumes on the daily snapshot, these are identity facts,
    # so they live here and can be aggregated directly (e.g. assets per country).
    country: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_cap_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_daily_turnover_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    history_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    criteria_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    snapshots: Mapped[list[AssetDailySnapshot]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AssetDailySnapshot(Base):
    """A per-asset, per-calendar-day snapshot backing the details view.

    Holds native-currency profile fields plus the price history as a JSONB
    array of ``{"date": "YYYY-MM-DD", "close": float}`` objects. One row per
    asset per UTC calendar day, enforced by the ``(asset_id, snapshot_date)``
    unique constraint, which doubles as the once-per-day cache key.
    """

    __tablename__ = "asset_daily_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "snapshot_date",
            name="uq_asset_daily_snapshot_asset_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # The UTC calendar day the snapshot data represents.
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Native trading currency (ISO code), copied from the asset at fetch time.
    currency: Mapped[str] = mapped_column(String, nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Time-varying trading volumes backing the detail-page panel, captured from
    # the provider at fetch time. Both nullable: any field the provider omits is
    # stored as NULL. Volumes use BigInteger because share volumes routinely
    # exceed the 32-bit range. The stable profile fields (country, city,
    # employees, website) live on the ``Asset`` row, not here.
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    price_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    asset: Mapped[Asset] = relationship(back_populates="snapshots")
