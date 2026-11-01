"""Feature/label assembly and settings-default tests for the price-ML capability."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from cadence.config import Settings
from cadence.price_ml import features
from cadence.price_ml.constants import FEATURE_COLUMNS
from cadence.price_ml.features import LABEL_COLUMN


def _business_days(n: int, *, start: date = date(2020, 1, 1)) -> list[date]:
    """Return ``n`` consecutive weekday dates starting at ``start``."""
    out: list[date] = []
    cursor = start
    while len(out) < n:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _synthetic_closes(
    n: int, *, seed: int = 7, amplitude: float = 8.0
) -> list[tuple[date, float]]:
    """A deterministic sinusoid-plus-noise close series with both up/down moves."""
    rng = np.random.default_rng(seed)
    days = _business_days(n)
    closes: list[tuple[date, float]] = []
    for i, d in enumerate(days):
        level = 100.0 + amplitude * math.sin(i / 11.0) + rng.normal(0.0, 0.3)
        closes.append((d, round(float(level), 4)))
    return closes


def test_build_features_columns_and_shape() -> None:
    closes = _synthetic_closes(300)
    frame = features.build_features(closes)

    assert list(frame.columns) == list(FEATURE_COLUMNS)
    assert len(frame) == len(closes)
    # Warmup rows (before the 200-day SMA is defined) are NaN; later rows complete.
    assert frame[list(FEATURE_COLUMNS)].notna().all(axis=1).any()


def test_build_features_deterministic() -> None:
    closes = _synthetic_closes(300)
    first = features.build_features(closes)
    second = features.build_features(closes)

    assert first.equals(second)
    assert first.columns.tolist() == list(FEATURE_COLUMNS)


def test_latest_feature_row_requires_enough_history() -> None:
    # Fewer bars than the long moving-average window -> no fully-defined row.
    short = _synthetic_closes(120)
    assert features.latest_feature_row(short) is None

    enough = _synthetic_closes(300)
    row = features.latest_feature_row(enough)
    assert row is not None
    assert not row[list(FEATURE_COLUMNS)].isna().any()


def test_latest_feature_row_empty_series() -> None:
    assert features.latest_feature_row([]) is None


def test_forward_return_label_sign_and_tail_nan() -> None:
    closes = _synthetic_closes(260)
    horizon = 21
    label = features.forward_return_label(closes, horizon)

    # The final `horizon` rows have no forward close and are NaN.
    assert label.iloc[-horizon:].isna().all()
    assert set(label.dropna().unique()).issubset({0.0, 1.0})

    # Spot-check one row against the raw forward return.
    series = features._close_series(closes)
    idx = 50
    fwd = series.iloc[idx + horizon] / series.iloc[idx] - 1.0
    assert label.iloc[idx] == (1.0 if fwd > 0 else 0.0)


def test_build_training_frame_has_no_missing_values() -> None:
    closes = _synthetic_closes(300)
    frame = features.build_training_frame(closes, horizon=21)

    assert not frame.empty
    assert not frame[[*FEATURE_COLUMNS, LABEL_COLUMN]].isna().any().any()
    assert LABEL_COLUMN in frame.columns


def test_build_training_frame_insufficient_history_is_empty() -> None:
    frame = features.build_training_frame(_synthetic_closes(120), horizon=21)
    assert frame.empty


def test_price_ml_settings_defaults() -> None:
    # Declared defaults, read without env overrides.
    fields = Settings.model_fields
    assert fields["PRICE_ML_HORIZON_DAYS"].default == 21
    assert fields["PRICE_ML_RETRAIN_DAYS"].default == 7
    assert fields["PRICE_ML_MIN_BAR_COUNT"].default == 260
    assert fields["PRICE_ML_STALENESS_DAYS"].default == 7
    assert fields["PRICE_ML_SEED"].default == 42
    assert fields["PRICE_ML_MODEL_VERSION"].default == "price-ml-v1"
    assert fields["PRICE_ML_MODEL_DIR"].default == "var/price_ml"
