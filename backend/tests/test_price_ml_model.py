"""Training, walk-forward validation, and artifact-cache tests for price-ML."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from tests.test_price_ml_features import _synthetic_closes

from cadence.price_ml import features, model
from cadence.price_ml.constants import FEATURE_COLUMNS
from cadence.price_ml.model import SAMPLE_DATE_COLUMN, CachedModel


def _pooled_frame(
    *, seeds: tuple[int, ...] = (1, 2, 3), n: int = 400, horizon: int = 21
) -> pd.DataFrame:
    """Assemble a pooled training frame from several synthetic assets."""
    frames: list[pd.DataFrame] = []
    for seed in seeds:
        closes = _synthetic_closes(n, seed=seed)
        frame = features.build_training_frame(closes, horizon)
        frame = frame.copy()
        frame[SAMPLE_DATE_COLUMN] = frame.index
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_train_model_and_predict_deterministic() -> None:
    pooled = _pooled_frame()
    horizon = 21

    first = model.train_model(
        pooled, horizon=horizon, model_version="price-ml-v1", seed=42
    )
    second = model.train_model(
        pooled, horizon=horizon, model_version="price-ml-v1", seed=42
    )

    assert first.feature_columns == tuple(FEATURE_COLUMNS)
    assert first.horizon_days == horizon

    row = features.latest_feature_row(_synthetic_closes(400, seed=1))
    assert row is not None
    p1 = model.predict_proba_up(first, row)
    p2 = model.predict_proba_up(second, row)
    assert 0.0 <= p1 <= 1.0
    assert p1 == p2  # identical seed + data -> identical probability


def test_train_model_requires_two_classes() -> None:
    pooled = _pooled_frame()
    pooled[features.LABEL_COLUMN] = 1.0  # collapse to a single class
    with pytest.raises(ValueError):
        model.train_model(pooled, horizon=21, model_version="v", seed=42)


def test_walk_forward_accuracy_deterministic_and_bounded() -> None:
    pooled = _pooled_frame()
    acc1 = model.walk_forward_accuracy(pooled, 21, seed=42)
    acc2 = model.walk_forward_accuracy(pooled, 21, seed=42)

    assert acc1 is not None
    assert acc1 == acc2
    assert 0.0 <= acc1 <= 1.0


def test_walk_forward_purges_overlapping_labels() -> None:
    pooled = _pooled_frame()
    # A horizon so large its purge window swallows every pre-test sample: no fold
    # can keep enough purged training data, so there is no valid accuracy.
    assert model.walk_forward_accuracy(pooled, 1_000, seed=42) is None


def test_walk_forward_accuracy_insufficient_history() -> None:
    pooled = _pooled_frame(seeds=(1,), n=260)
    tiny = pooled.head(3)
    assert model.walk_forward_accuracy(tiny, 21, seed=42) is None


def test_cache_round_trip_and_reuse(tmp_path) -> None:
    pooled = _pooled_frame()
    cached = model.train_model(
        pooled, horizon=21, model_version="price-ml-v1", seed=42
    )
    model.save_model(cached, str(tmp_path))

    loaded = model.load_cached_model(
        str(tmp_path), model_version="price-ml-v1", horizon_days=21
    )
    assert loaded is not None
    assert loaded.model_version == "price-ml-v1"
    assert loaded.feature_columns == tuple(FEATURE_COLUMNS)

    # A recent cache within the retrain cadence is reused, not retrained.
    assert not model.should_retrain(
        loaded, today=loaded.trained_on, retrain_days=7
    )
    assert not model.should_retrain(
        loaded, today=loaded.trained_on + timedelta(days=6), retrain_days=7
    )


def test_cache_incompatible_metadata_triggers_retrain(tmp_path) -> None:
    pooled = _pooled_frame()
    cached = model.train_model(
        pooled, horizon=21, model_version="price-ml-v1", seed=42
    )
    model.save_model(cached, str(tmp_path))

    # Wrong version -> treated as absent (None) -> retrain.
    assert (
        model.load_cached_model(
            str(tmp_path), model_version="price-ml-v2", horizon_days=21
        )
        is None
    )
    # Wrong horizon -> treated as absent (None) -> retrain.
    assert (
        model.load_cached_model(
            str(tmp_path), model_version="price-ml-v1", horizon_days=42
        )
        is None
    )
    assert model.should_retrain(None, today=date(2026, 1, 15), retrain_days=7)


def test_cache_missing_file_returns_none(tmp_path) -> None:
    assert (
        model.load_cached_model(
            str(tmp_path / "empty"), model_version="price-ml-v1", horizon_days=21
        )
        is None
    )


def test_retrain_when_cache_older_than_cadence(tmp_path) -> None:
    pooled = _pooled_frame()
    cached = model.train_model(
        pooled, horizon=21, model_version="price-ml-v1", seed=42
    )
    stale = CachedModel(
        model=cached.model,
        model_version=cached.model_version,
        feature_columns=cached.feature_columns,
        horizon_days=cached.horizon_days,
        trained_on=date(2026, 1, 15) - timedelta(days=10),
        recent_oos_accuracy=cached.recent_oos_accuracy,
    )
    assert model.should_retrain(stale, today=date(2026, 1, 15), retrain_days=7)
