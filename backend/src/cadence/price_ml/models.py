"""SQLAlchemy 2.0 ORM for the stored price-ML signal (one row per asset).

Schema is owned by Alembic; this model is the source of truth for autogenerate.
One table ``price_ml_signal`` holds the latest learned price-direction signal per
asset (unique on ``asset_id``): the predicted direction and its probability, the
recent out-of-sample accuracy from the walk-forward evaluation, the horizon, the
as-of date, the model version, the date of the features it was drawn from, and
the bar count behind those features. Each precompute replaces the asset's row, so
there is exactly one current signal per asset.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base


class PriceMlSignal(Base):
    """Latest learned price-direction signal for one asset (one row per asset)."""

    __tablename__ = "price_ml_signal"
    __table_args__ = (UniqueConstraint("asset_id", name="uq_price_ml_signal_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Date the signal was produced (the precompute's as-of date).
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Forward-return horizon, in trading days, the model was trained to predict.
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Predicted direction of the forward return: ``up`` or ``down``.
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    #: Probability of the predicted direction (model confidence, 0.5..1.0).
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    #: Recent out-of-sample accuracy from the purged/embargoed walk-forward.
    #: NULL when the evaluation could not run (too little history for a split).
    recent_oos_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Version of the model/feature schema that produced the signal.
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Date of the latest bar the inference features were drawn from.
    feature_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    #: Number of bars behind the asset's features.
    bar_count: Mapped[int] = mapped_column(Integer, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
