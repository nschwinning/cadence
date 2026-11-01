"""Price-ML precompute, signal storage/reads, and annotation resolution.

The precompute assembles each eligible asset's features from its stored price
history, trains the pooled classifier (or reuses the cached one on a non-retrain
night), predicts a per-asset direction, and stores one signal row per asset —
isolating per-asset failures. Reads mirror the technical-indicators seam
(``get_latest_ml_signal`` / ``get_latest_ml_signals``). The rebalance flow
resolves per-ticker annotations through :func:`resolve_signal_annotations`, which
applies the staleness bound and yields an explicit "unavailable" marker rather
than ever fabricating a signal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.config import settings
from cadence.price_history.models import PriceHistory
from cadence.price_ml import constants as c
from cadence.price_ml import features, model
from cadence.price_ml.constants import SignalDirection, SignalStatus
from cadence.price_ml.features import LABEL_COLUMN
from cadence.price_ml.model import SAMPLE_DATE_COLUMN, CachedModel
from cadence.price_ml.models import PriceMlSignal

logger = logging.getLogger(__name__)

#: The explicit marker for an asset with no usable price-ML signal. Copied per
#: attach so callers never share one mutable object.
_PRICE_ML_UNAVAILABLE: dict[str, Any] = {"status": SignalStatus.UNAVAILABLE.value}


@dataclass(frozen=True)
class PriceMlRefreshSummary:
    """Outcome of a price-ML precompute run."""

    assets_processed: int
    assets_failed: int
    assets_skipped: int
    trained: bool
    model_version: str


def _load_closes(session: Session, asset_id: int) -> list[tuple[date, float]]:
    """Return an asset's stored (date, close) history ordered oldest first."""
    rows = session.execute(
        select(PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.asset_id == asset_id)
        .order_by(PriceHistory.date)
    ).all()
    return [(row[0], float(row[1])) for row in rows]


def _assemble_pooled(
    eligible: Sequence[tuple[Asset, list[tuple[date, float]]]],
    horizon: int,
) -> pd.DataFrame:
    """Concatenate every eligible asset's training rows into one pooled frame."""
    frames: list[pd.DataFrame] = []
    for _asset, closes in eligible:
        frame = features.build_training_frame(closes, horizon)
        if frame.empty:
            continue
        frame = frame.copy()
        frame[SAMPLE_DATE_COLUMN] = frame.index
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def record_signal(
    session: Session,
    *,
    asset_id: int,
    as_of_date: date,
    horizon_days: int,
    direction: str,
    probability: float,
    recent_oos_accuracy: float | None,
    model_version: str,
    feature_as_of: date,
    bar_count: int,
) -> PriceMlSignal:
    """Replace an asset's stored signal with a fresh row and commit."""
    session.execute(delete(PriceMlSignal).where(PriceMlSignal.asset_id == asset_id))
    row = PriceMlSignal(
        asset_id=asset_id,
        as_of_date=as_of_date,
        horizon_days=horizon_days,
        direction=direction,
        probability=probability,
        recent_oos_accuracy=recent_oos_accuracy,
        model_version=model_version,
        feature_as_of=feature_as_of,
        bar_count=bar_count,
    )
    session.add(row)
    session.commit()
    return row


def get_latest_ml_signal(session: Session, asset_id: int) -> PriceMlSignal | None:
    """Return the stored signal for one asset, or ``None`` if not computed."""
    return session.execute(
        select(PriceMlSignal).where(PriceMlSignal.asset_id == asset_id)
    ).scalar_one_or_none()


def get_latest_ml_signals(
    session: Session, asset_ids: Sequence[int]
) -> dict[int, PriceMlSignal]:
    """Return stored signals keyed by asset id (missing ids simply absent)."""
    if not asset_ids:
        return {}
    rows = session.execute(
        select(PriceMlSignal).where(PriceMlSignal.asset_id.in_(list(asset_ids)))
    ).scalars()
    return {row.asset_id: row for row in rows}


def signal_annotation(
    signal: PriceMlSignal | None, *, as_of: date, staleness_days: int
) -> dict[str, Any]:
    """The per-ticker price-ML block, or an "unavailable" marker.

    Yields the explicit unavailable marker — never an invented direction — when
    there is no stored signal or the stored signal is older than the staleness
    bound. Otherwise shapes the stored prediction into a compact advisory block.
    """
    if signal is None or (as_of - signal.as_of_date).days > staleness_days:
        return dict(_PRICE_ML_UNAVAILABLE)
    return {
        "status": SignalStatus.AVAILABLE.value,
        "direction": signal.direction,
        "probability": round(signal.probability, 4),
        "recent_oos_accuracy": (
            round(signal.recent_oos_accuracy, 4)
            if signal.recent_oos_accuracy is not None
            else None
        ),
        "as_of": signal.as_of_date.isoformat(),
        "horizon_days": signal.horizon_days,
    }


def resolve_signal_annotations(
    session: Session,
    asset_ids_by_ticker: Mapping[str, int],
    *,
    as_of: date | None = None,
    staleness_days: int = settings.PRICE_ML_STALENESS_DAYS,
) -> dict[str, dict[str, Any]]:
    """Resolve a ticker→annotation map, applying the staleness bound per ticker."""
    as_of = as_of or c.today()
    signals = get_latest_ml_signals(session, list(asset_ids_by_ticker.values()))
    return {
        ticker: signal_annotation(
            signals.get(asset_id), as_of=as_of, staleness_days=staleness_days
        )
        for ticker, asset_id in asset_ids_by_ticker.items()
    }


def refresh_signals(
    session: Session,
    *,
    today: date | None = None,
    horizon: int | None = None,
    retrain_days: int | None = None,
    min_bar_count: int | None = None,
    seed: int | None = None,
    model_version: str | None = None,
    model_dir: str | None = None,
) -> PriceMlRefreshSummary:
    """Train-or-reuse the pooled model and store one signal row per eligible asset.

    Assets below the minimum bar count are skipped. The model is retrained when
    the cached one is missing, incompatible, or older than the retrain cadence;
    otherwise the cached model is reused so the stored signal is stable between
    retrains. Per-asset prediction failures are isolated and do not abort the run.

    Unset arguments fall back to live settings (resolved at call time, so runtime
    overrides and tests take effect).
    """
    as_of = today or c.today()
    horizon = horizon if horizon is not None else settings.PRICE_ML_HORIZON_DAYS
    retrain_days = (
        retrain_days if retrain_days is not None else settings.PRICE_ML_RETRAIN_DAYS
    )
    min_bar_count = (
        min_bar_count
        if min_bar_count is not None
        else settings.PRICE_ML_MIN_BAR_COUNT
    )
    seed = seed if seed is not None else settings.PRICE_ML_SEED
    model_version = (
        model_version if model_version is not None else settings.PRICE_ML_MODEL_VERSION
    )
    model_dir = model_dir if model_dir is not None else settings.PRICE_ML_MODEL_DIR
    assets = list(session.execute(select(Asset)).scalars())

    eligible: list[tuple[Asset, list[tuple[date, float]]]] = []
    skipped = 0
    for asset in assets:
        closes = _load_closes(session, asset.id)
        if len(closes) < min_bar_count:
            skipped += 1
            continue
        eligible.append((asset, closes))

    cached = model.load_cached_model(
        model_dir, model_version=model_version, horizon_days=horizon
    )
    trained_model: CachedModel | None = cached
    trained = False
    if model.should_retrain(cached, today=as_of, retrain_days=retrain_days):
        pooled = _assemble_pooled(eligible, horizon)
        if (
            not pooled.empty
            and pooled[LABEL_COLUMN].nunique() >= 2
            and len(pooled) >= model.MIN_TRAIN_SAMPLES
        ):
            try:
                trained_model = model.train_model(
                    pooled, horizon=horizon, model_version=model_version, seed=seed
                )
                model.save_model(trained_model, model_dir)
                trained = True
            except Exception:
                logger.exception("price-ML training failed; falling back to cache")
                trained_model = cached

    if trained_model is None:
        # Nothing to predict with — no compatible cache and training did not run.
        return PriceMlRefreshSummary(
            assets_processed=0,
            assets_failed=0,
            assets_skipped=skipped,
            trained=trained,
            model_version=model_version,
        )

    processed = 0
    failed = 0
    for asset, closes in eligible:
        try:
            row = features.latest_feature_row(closes)
            if row is None:
                skipped += 1
                continue
            proba_up = model.predict_proba_up(trained_model, row)
            if proba_up >= 0.5:
                direction = SignalDirection.UP.value
                probability = proba_up
            else:
                direction = SignalDirection.DOWN.value
                probability = 1.0 - proba_up
            feature_as_of = pd.Timestamp(row.name).date()
            record_signal(
                session,
                asset_id=asset.id,
                as_of_date=as_of,
                horizon_days=horizon,
                direction=direction,
                probability=float(probability),
                recent_oos_accuracy=trained_model.recent_oos_accuracy,
                model_version=trained_model.model_version,
                feature_as_of=feature_as_of,
                bar_count=len(closes),
            )
            processed += 1
        except Exception:
            failed += 1
            logger.exception("price-ML prediction failed for %s", asset.ticker)

    return PriceMlRefreshSummary(
        assets_processed=processed,
        assets_failed=failed,
        assets_skipped=skipped,
        trained=trained,
        model_version=trained_model.model_version,
    )
