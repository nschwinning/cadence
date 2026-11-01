"""Deterministic feature and label assembly from stored daily closes.

Features are built from an asset's already-stored ``price_history`` series — no
additional market-data fetch beyond what the technical-indicators precompute
already performs. The feature set is the lagged trailing returns plus a handful
of scale-free indicators (RSI, a normalised MACD histogram, realised volatility,
moving-average ratios, Bollinger %b) derived from the closes, so the same feature
can be computed at every historical row (for training) and at the latest row (for
inference). Assembly is a pure function of the input series — deterministic given
fixed inputs.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from cadence.price_ml import constants as c

#: Column name for the training label.
LABEL_COLUMN = "label"


def _close_series(closes: Sequence[tuple[date, float]]) -> pd.Series:
    """Return a float close series indexed by date, sorted ascending and deduped."""
    if not closes:
        return pd.Series(dtype="float64")
    frame = pd.DataFrame(closes, columns=["date", "close"])
    frame = frame.drop_duplicates(subset="date", keep="last").sort_values("date")
    series = pd.Series(
        frame["close"].to_numpy(dtype="float64"),
        index=pd.DatetimeIndex(frame["date"]),
        name="close",
    )
    return series


def _rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI (0..100)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # When there are no losses the ratio is +inf -> RSI 100; when no gains, RSI 0.
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi = rsi.where(avg_gain != 0.0, rsi.where(avg_loss != 0.0, 50.0))
    return rsi


def build_features(closes: Sequence[tuple[date, float]]) -> pd.DataFrame:
    """Build the full feature frame indexed by date.

    Warmup rows whose indicators are not yet defined are retained as NaN; callers
    drop them. Columns are exactly :data:`constants.FEATURE_COLUMNS` in order.
    """
    close = _close_series(closes)
    if close.empty:
        return pd.DataFrame(columns=list(c.FEATURE_COLUMNS))

    returns = close.pct_change()
    data: dict[str, pd.Series] = {}

    for window in c.LAG_RETURN_WINDOWS:
        data[f"ret_{window}d"] = close.pct_change(window)

    data["rsi_14"] = _rsi(close, c.RSI_PERIOD)

    ema_fast = close.ewm(span=c.MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=c.MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=c.MACD_SIGNAL, adjust=False).mean()
    # Scale-free: normalise the histogram by price so it pools across assets.
    data["macd_hist"] = (macd_line - macd_signal) / close

    data["vol_21"] = returns.rolling(c.VOL_WINDOW).std()

    sma_short = close.rolling(c.SMA_SHORT).mean()
    sma_long = close.rolling(c.SMA_LONG).mean()
    data["close_sma50"] = close / sma_short - 1.0
    data["close_sma200"] = close / sma_long - 1.0
    data["sma50_sma200"] = sma_short / sma_long - 1.0

    bb_mid = close.rolling(c.BB_PERIOD).mean()
    bb_std = close.rolling(c.BB_PERIOD).std()
    bb_lower = bb_mid - c.BB_STD * bb_std
    bb_width = 2.0 * c.BB_STD * bb_std
    data["bb_pctb"] = (close - bb_lower) / bb_width

    frame = pd.DataFrame(data, index=close.index)
    frame = frame[list(c.FEATURE_COLUMNS)]
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame


def forward_return_label(
    closes: Sequence[tuple[date, float]], horizon: int
) -> pd.Series:
    """Binary label: 1 when the forward ``horizon``-day return is positive, else 0.

    NaN where the forward close is unavailable (the final ``horizon`` rows).
    """
    close = _close_series(closes)
    if close.empty:
        return pd.Series(dtype="float64", name=LABEL_COLUMN)
    forward = close.shift(-horizon) / close - 1.0
    label = (forward > 0.0).astype("float64")
    label[forward.isna()] = np.nan
    label.name = LABEL_COLUMN
    return label


def build_training_frame(
    closes: Sequence[tuple[date, float]], horizon: int
) -> pd.DataFrame:
    """Feature frame joined with the forward-return label, warmup/tail rows dropped.

    Rows missing any feature (warmup) or the label (final ``horizon`` rows) are
    excluded, so no model ever trains on fabricated or incomplete data.
    """
    features = build_features(closes)
    if features.empty:
        return features.assign(**{LABEL_COLUMN: pd.Series(dtype="float64")})
    label = forward_return_label(closes, horizon)
    frame = features.join(label, how="left")
    frame = frame.dropna(subset=[*c.FEATURE_COLUMNS, LABEL_COLUMN])
    return frame


def latest_feature_row(closes: Sequence[tuple[date, float]]) -> pd.Series | None:
    """The most recent fully-defined feature row (for inference), or ``None``.

    Returns ``None`` when no row has all features defined (insufficient history).
    """
    features = build_features(closes)
    if features.empty:
        return None
    complete = features.dropna(subset=list(c.FEATURE_COLUMNS))
    if complete.empty:
        return None
    return complete.iloc[-1]
