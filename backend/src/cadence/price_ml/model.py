"""Pooled gradient-boosted model: training, walk-forward evaluation, caching.

A single :class:`~sklearn.ensemble.HistGradientBoostingClassifier` is trained
across the combined feature rows of all eligible assets to predict the sign of
the forward-return label. Reliability is measured with a purged and embargoed
walk-forward (samples whose label horizon overlaps the evaluation window are
purged), and the resulting recent out-of-sample accuracy is cached with the
model. The model is persisted (joblib) with a metadata-compatibility gate so an
incompatible cache (different model version, feature schema, or horizon) triggers
a retrain rather than being silently reused.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from cadence.price_ml import constants as c
from cadence.price_ml.features import LABEL_COLUMN

logger = logging.getLogger(__name__)

#: Pooled-frame column holding each sample's feature-row (as-of) date.
SAMPLE_DATE_COLUMN = "sample_date"

# --- Walk-forward evaluation shape (deterministic, non-configurable) ---------
WALK_FORWARD_SPLITS = 4
EMBARGO_TRADING_DAYS = 2
MIN_TRAIN_SAMPLES = 50
MIN_TEST_SAMPLES = 10

_CACHE_FILENAME = "price_ml_model.joblib"


@dataclass(frozen=True)
class CachedModel:
    """A trained model plus the metadata that gates its reuse."""

    model: HistGradientBoostingClassifier
    model_version: str
    feature_columns: tuple[str, ...]
    horizon_days: int
    trained_on: date
    recent_oos_accuracy: float | None


def _trading_days_to_calendar(trading_days: int) -> int:
    """Approximate a trading-day span as calendar days (5 trading ≈ 7 calendar)."""
    return math.ceil(trading_days * 7 / 5)


def _new_classifier(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(random_state=seed)


def _fit(frame: pd.DataFrame, seed: int) -> HistGradientBoostingClassifier:
    features = frame[list(c.FEATURE_COLUMNS)].to_numpy(dtype="float64")
    labels = frame[LABEL_COLUMN].to_numpy(dtype="int64")
    model = _new_classifier(seed)
    model.fit(features, labels)
    return model


def _accuracy(model: HistGradientBoostingClassifier, frame: pd.DataFrame) -> float:
    features = frame[list(c.FEATURE_COLUMNS)].to_numpy(dtype="float64")
    labels = frame[LABEL_COLUMN].to_numpy(dtype="int64")
    predictions = model.predict(features)
    return float(np.mean(predictions == labels))


def walk_forward_accuracy(
    pooled: pd.DataFrame, horizon: int, *, seed: int
) -> float | None:
    """Recent out-of-sample accuracy from a purged/embargoed walk-forward.

    Rolls an expanding past-train / future-test window across the pooled samples'
    dates. For each fold, train samples whose label horizon overlaps (or is within
    the embargo of) the test window's start are purged so the reported accuracy is
    not inflated by overlapping multi-period labels. Returns the mean accuracy over
    the valid folds, or ``None`` when there is too little history to form one.
    """
    if pooled.empty:
        return None
    dates = sorted(pd.unique(pooled[SAMPLE_DATE_COLUMN]))
    if len(dates) < WALK_FORWARD_SPLITS + 1:
        return None

    purge = _trading_days_to_calendar(horizon + EMBARGO_TRADING_DAYS)
    # Partition the timeline into WALK_FORWARD_SPLITS + 1 contiguous blocks; fold i
    # tests on block i and trains on everything before it (minus the purge zone).
    block_bounds = np.array_split(np.array(dates), WALK_FORWARD_SPLITS + 1)
    sample_dates = pd.to_datetime(pooled[SAMPLE_DATE_COLUMN])

    accuracies: list[float] = []
    for i in range(1, len(block_bounds)):
        test_block = block_bounds[i]
        if len(test_block) == 0:
            continue
        test_start = pd.Timestamp(test_block[0])
        test_end = pd.Timestamp(test_block[-1])
        test_mask = (sample_dates >= test_start) & (sample_dates <= test_end)
        purge_before = test_start - pd.Timedelta(days=purge)
        train_mask = sample_dates < purge_before

        train = pooled[train_mask]
        test = pooled[test_mask]
        if len(train) < MIN_TRAIN_SAMPLES or len(test) < MIN_TEST_SAMPLES:
            continue
        if train[LABEL_COLUMN].nunique() < 2:
            continue
        model = _fit(train, seed)
        accuracies.append(_accuracy(model, test))

    if not accuracies:
        return None
    return float(np.mean(accuracies))


def train_model(
    pooled: pd.DataFrame,
    *,
    horizon: int,
    model_version: str,
    seed: int,
) -> CachedModel:
    """Train the pooled classifier on all samples and evaluate it walk-forward."""
    if pooled.empty or pooled[LABEL_COLUMN].nunique() < 2:
        raise ValueError("cannot train price-ML model: need samples with both classes")
    oos_accuracy = walk_forward_accuracy(pooled, horizon, seed=seed)
    model = _fit(pooled, seed)
    return CachedModel(
        model=model,
        model_version=model_version,
        feature_columns=tuple(c.FEATURE_COLUMNS),
        horizon_days=horizon,
        trained_on=c.today(),
        recent_oos_accuracy=oos_accuracy,
    )


def predict_proba_up(cached: CachedModel, feature_row: pd.Series) -> float:
    """Return the model's probability that the forward return is positive."""
    features = feature_row[list(c.FEATURE_COLUMNS)].to_numpy(dtype="float64").reshape(1, -1)
    classes = list(cached.model.classes_)
    proba = cached.model.predict_proba(features)[0]
    if 1 in classes:
        return float(proba[classes.index(1)])
    # Degenerate single-class model: it only ever saw one label.
    return 1.0 if classes and classes[0] == 1 else 0.0


# --- Artifact cache ----------------------------------------------------------


def cache_path(model_dir: str) -> Path:
    return Path(model_dir) / _CACHE_FILENAME


def save_model(cached: CachedModel, model_dir: str) -> None:
    """Persist the trained model and its metadata to the cache directory."""
    path = cache_path(model_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(cached, path)


def load_cached_model(
    model_dir: str, *, model_version: str, horizon_days: int
) -> CachedModel | None:
    """Load the cached model, or ``None`` when absent or incompatible.

    The metadata-compatibility gate rejects a cache whose model version, feature
    schema, or horizon does not match the current configuration, so a schema or
    version change transparently triggers a retrain instead of a silent mismatch.
    """
    path = cache_path(model_dir)
    if not path.exists():
        return None
    try:
        cached: Any = joblib.load(path)
    except Exception:
        logger.exception("failed to load cached price-ML model at %s", path)
        return None
    if not isinstance(cached, CachedModel):
        return None
    if (
        cached.model_version != model_version
        or cached.horizon_days != horizon_days
        or tuple(cached.feature_columns) != tuple(c.FEATURE_COLUMNS)
    ):
        return None
    return cached


def should_retrain(
    cached: CachedModel | None, *, today: date, retrain_days: int
) -> bool:
    """Whether to retrain: no compatible cache, or the cache is older than cadence."""
    if cached is None:
        return True
    return (today - cached.trained_on).days >= retrain_days
