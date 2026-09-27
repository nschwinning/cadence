"""SQLAlchemy 2.0 ORM models for technical-indicator storage.

Schema is owned by Alembic; these models are the source of truth for
autogenerate. Two tables:

* ``technical_indicator`` — the **latest snapshot per asset** (unique on
  ``asset_id``): the fixed close+volume indicator set (all nullable — an
  indicator is NULL when history is insufficient), the deterministic gate verdict
  and its sub-verdicts, and the boolean reversal flags. Recompute replaces the
  single row, so a read always sees the newest snapshot.
* ``technical_indicator_run`` — a run-audit row: status, timing, and per-asset
  processed/failed counts.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base
from cadence.technical_indicators.constants import RunPhase


class TechnicalIndicator(Base):
    """Latest indicator snapshot for one asset (one row per asset)."""

    __tablename__ = "technical_indicator"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_technical_indicator_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The calendar day of the latest bar the snapshot was computed from.
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Indicator values (nullable: NULL when history is insufficient) ----
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma_200: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_sma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma50_sma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma200_slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd_hist: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_14: Mapped[float | None] = mapped_column(Float, nullable=True)
    roc_120: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv: Mapped[float | None] = mapped_column(Float, nullable=True)
    obv_change_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_ratio_50: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_high_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    drawdown_from_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    hvol_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_pctb: Mapped[float | None] = mapped_column(Float, nullable=True)
    bb_width: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Deterministic uptrend gate verdict + sub-verdicts -----------------
    gate_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    regime_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    momentum_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    obv_rising: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # --- Deterministic reversal flags --------------------------------------
    rev_macd_hist_rollover: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rev_rsi_rollover: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rev_return_decel: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rev_obv_price_divergence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rev_sma200_slope_flattening: Mapped[bool] = mapped_column(Boolean, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TechnicalIndicatorRun(Base):
    """Audit row for a single nightly indicator precompute run."""

    __tablename__ = "technical_indicator_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One of cadence.technical_indicators.constants.RunPhase values.
    status: Mapped[str] = mapped_column(
        SQLEnum(
            RunPhase,
            native_enum=False,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        server_default=RunPhase.QUEUED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assets_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    assets_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
