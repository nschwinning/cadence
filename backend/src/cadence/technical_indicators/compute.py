"""Pure pandas/numpy technical-indicator engine (close+volume subset).

Ported from quantara's ``compute_indicator_frame``, restricted to the indicators
derivable from an adjusted-close + volume series (no OHLC-only features such as
ATR/ADX/Stochastic). :func:`compute_snapshot` takes one asset's date-ordered
daily bars and returns the **latest** bar's :class:`IndicatorSnapshot`: the fixed
indicator set, the deterministic uptrend :class:`TrendGate`, and the boolean
:class:`ReversalFlags`.

Conventions carried over from quantara:

* All moving-average / momentum / volatility features use the split/dividend
  adjusted close (``adj_close`` when present on the bar, else ``close``).
* Every window is strictly backward-looking, so a value never depends on a
  future bar.
* Warmup (window longer than available history) and degenerate bars yield
  ``NaN``/``inf`` which are normalised to ``None`` — an absent value, never a
  failure. A gate condition reading an absent value evaluates to fail.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from cadence.assets.market_data import HistoryBar
from cadence.technical_indicators import constants as c


@dataclass(frozen=True)
class TrendGate:
    """The deterministic uptrend verdict and its component sub-verdicts."""

    regime_pass: bool
    momentum_pass: bool
    obv_rising: bool
    gate_pass: bool


@dataclass(frozen=True)
class ReversalFlags:
    """Deterministic reversal booleans for a held position."""

    macd_hist_rollover: bool
    rsi_rollover: bool
    return_decel: bool
    obv_price_divergence: bool
    sma200_slope_flattening: bool


@dataclass(frozen=True)
class IndicatorSnapshot:
    """The latest-bar indicator values plus the derived gate and flags."""

    trading_date: date
    close: float | None
    sma_50: float | None
    sma_200: float | None
    close_sma200: float | None
    sma50_sma200: float | None
    sma200_slope: float | None
    ema_20: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_hist: float | None
    rsi_14: float | None
    roc_120: float | None
    obv: float | None
    obv_change_20d: float | None
    vol_ratio_50: float | None
    dist_high_52w: float | None
    drawdown_from_max: float | None
    hvol_20: float | None
    bb_pctb: float | None
    bb_width: float | None
    gate: TrendGate
    reversal_flags: ReversalFlags


def _wilder(series: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (SMMA); NaN until ``n`` observations are available."""
    values = series.to_numpy(dtype="float64")
    out = np.full(values.shape, np.nan)
    valid = ~np.isnan(values)
    if int(valid.sum()) < n:
        return pd.Series(out, index=series.index)
    cum = np.cumsum(valid)
    seed_pos = int(np.argmax(cum >= n))
    window = values[: seed_pos + 1]
    prev = float(np.nanmean(window[~np.isnan(window)][-n:]))
    out[seed_pos] = prev
    for i in range(seed_pos + 1, len(values)):
        x = values[i]
        if np.isnan(x):
            out[i] = prev
            continue
        prev = (prev * (n - 1) + x) / n
        out[i] = prev
    return pd.Series(out, index=series.index)


def _rsi(price: pd.Series, n: int) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder(gain, n)
    avg_loss = _wilder(loss, n)
    rs = avg_gain / avg_loss
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(avg_loss != 0.0, other=100.0)
    rsi = rsi.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), other=np.nan)
    return rsi.where(~avg_gain.isna())


def _clean(value: float | None) -> float | None:
    """Normalise NaN/inf to ``None`` and everything else to ``float``."""
    if value is None:
        return None
    fvalue = float(value)
    if math.isnan(fvalue) or math.isinf(fvalue):
        return None
    return fvalue


def _last(series: pd.Series) -> float | None:
    """The last value of a series as a clean ``float | None``."""
    if series.empty:
        return None
    return _clean(series.iloc[-1])


def compute_snapshot(bars: Sequence[HistoryBar]) -> IndicatorSnapshot | None:
    """Compute the latest indicator snapshot for one asset.

    Returns ``None`` only when ``bars`` is empty. Insufficient history for a
    given indicator yields an absent (``None``) value on the snapshot, not a
    failure; the gate reads absent values as fail.
    """
    if not bars:
        return None

    ordered = sorted(bars, key=lambda bar: bar.date)
    dates = [bar.date for bar in ordered]
    close = pd.Series([float(bar.close) for bar in ordered], dtype="float64")
    volume = pd.Series([float(bar.volume) for bar in ordered], dtype="float64")
    # Prefer the adjusted close; fall back to the raw close per-bar.
    p = pd.Series(
        [
            float(bar.adj_close) if bar.adj_close is not None else float(bar.close)
            for bar in ordered
        ],
        dtype="float64",
    )

    # --- Moving averages / trend ------------------------------------------
    sma_50 = p.rolling(c.SMA_SHORT).mean()
    sma_200 = p.rolling(c.SMA_LONG).mean()
    ema_20 = p.ewm(span=c.EMA_SPAN, adjust=False, min_periods=c.EMA_SPAN).mean()
    close_sma200 = p / sma_200
    sma50_sma200 = sma_50 / sma_200
    sma200_slope = sma_200 / sma_200.shift(c.SLOPE_WINDOW) - 1.0

    # --- Momentum ----------------------------------------------------------
    rsi_14 = _rsi(p, c.RSI_PERIOD)
    roc_120 = p / p.shift(c.ROC_PERIOD) - 1.0
    ema_fast = p.ewm(span=c.MACD_FAST, adjust=False, min_periods=c.MACD_FAST).mean()
    ema_slow = p.ewm(span=c.MACD_SLOW, adjust=False, min_periods=c.MACD_SLOW).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(
        span=c.MACD_SIGNAL, adjust=False, min_periods=c.MACD_SIGNAL
    ).mean()
    macd_hist = macd_line - macd_signal
    macd_hist_change = macd_hist.diff()

    # Return acceleration (momentum fading proxy).
    return_5d = p / p.shift(5) - 1.0
    return_accel = return_5d - return_5d.shift(5)

    # --- Distance / drawdown / volatility ---------------------------------
    roll_max_252 = p.rolling(c.HIGH_52W).max()
    dist_high_52w = p / roll_max_252 - 1.0
    drawdown_from_max = p / p.rolling(c.DRAWDOWN_PERIOD).max() - 1.0
    log_ret = np.log(p / p.shift(1))
    hvol_20 = log_ret.rolling(c.HVOL_PERIOD).std(ddof=1) * math.sqrt(c.TRADING_DAYS)

    # --- Bollinger --------------------------------------------------------
    mid = p.rolling(c.BB_PERIOD).mean()
    std = p.rolling(c.BB_PERIOD).std(ddof=0)
    upper = mid + c.BB_STD * std
    lower = mid - c.BB_STD * std
    band = (upper - lower).replace(0.0, np.nan)
    bb_width = band / mid.replace(0.0, np.nan)
    bb_pctb = (p - lower) / band

    # --- Volume -----------------------------------------------------------
    avg_vol_50 = volume.rolling(c.AVG_VOL_PERIOD).mean()
    vol_ratio_50 = volume / avg_vol_50.replace(0.0, np.nan)
    obv = (np.sign(close.diff()).fillna(0.0) * volume).cumsum()
    obv_change_20d = obv - obv.shift(c.OBV_CHANGE_WINDOW)

    snapshot = IndicatorSnapshot(
        trading_date=dates[-1],
        close=_last(close),
        sma_50=_last(sma_50),
        sma_200=_last(sma_200),
        close_sma200=_last(close_sma200),
        sma50_sma200=_last(sma50_sma200),
        sma200_slope=_last(sma200_slope),
        ema_20=_last(ema_20),
        macd_line=_last(macd_line),
        macd_signal=_last(macd_signal),
        macd_hist=_last(macd_hist),
        rsi_14=_last(rsi_14),
        roc_120=_last(roc_120),
        obv=_last(obv),
        obv_change_20d=_last(obv_change_20d),
        vol_ratio_50=_last(vol_ratio_50),
        dist_high_52w=_last(dist_high_52w),
        drawdown_from_max=_last(drawdown_from_max),
        hvol_20=_last(hvol_20),
        bb_pctb=_last(bb_pctb),
        bb_width=_last(bb_width),
        gate=_derive_gate(
            close=_last(close),
            sma_50=_last(sma_50),
            sma_200=_last(sma_200),
            sma200_slope=_last(sma200_slope),
            macd_hist=_last(macd_hist),
            rsi_14=_last(rsi_14),
            roc_120=_last(roc_120),
            obv_change_20d=_last(obv_change_20d),
        ),
        reversal_flags=_derive_reversal_flags(
            macd_hist_change=_last(macd_hist_change),
            rsi_series=rsi_14,
            return_accel=_last(return_accel),
            price_series=p,
            obv_series=obv,
            sma200_slope=_last(sma200_slope),
        ),
    )
    return snapshot


def _derive_gate(
    *,
    close: float | None,
    sma_50: float | None,
    sma_200: float | None,
    sma200_slope: float | None,
    macd_hist: float | None,
    rsi_14: float | None,
    roc_120: float | None,
    obv_change_20d: float | None,
) -> TrendGate:
    """Deterministic uptrend gate. Any absent required input fails its side."""
    regime_pass = (
        close is not None
        and sma_200 is not None
        and sma_50 is not None
        and sma200_slope is not None
        and close > sma_200
        and sma_50 > sma_200
        and sma200_slope >= c.SMA_SLOPE_MIN
    )
    momentum_pass = (
        macd_hist is not None
        and rsi_14 is not None
        and roc_120 is not None
        and macd_hist > c.MACD_HIST_MIN
        and rsi_14 > c.RSI_MOMENTUM_MIN
        and roc_120 > c.ROC_MOMENTUM_MIN
    )
    obv_rising = obv_change_20d is not None and obv_change_20d > 0.0
    return TrendGate(
        regime_pass=regime_pass,
        momentum_pass=momentum_pass,
        obv_rising=obv_rising,
        gate_pass=regime_pass and momentum_pass,
    )


def _derive_reversal_flags(
    *,
    macd_hist_change: float | None,
    rsi_series: pd.Series,
    return_accel: float | None,
    price_series: pd.Series,
    obv_series: pd.Series,
    sma200_slope: float | None,
) -> ReversalFlags:
    """Deterministic reversal flags derived from the computed series."""
    # MACD histogram turned down vs the prior period.
    macd_hist_rollover = macd_hist_change is not None and macd_hist_change < 0.0

    # RSI peaked in a high band and turned down.
    rsi_rollover = False
    if len(rsi_series) >= 2:
        prev = _clean(rsi_series.iloc[-2])
        curr = _clean(rsi_series.iloc[-1])
        if prev is not None and curr is not None:
            rsi_rollover = prev >= c.RSI_OVERBOUGHT and curr < prev

    # Return acceleration non-positive → momentum fading.
    return_decel = return_accel is not None and return_accel <= 0.0

    # Price makes a new N-day high while OBV does not (simple divergence proxy).
    obv_price_divergence = _obv_price_divergence(price_series, obv_series)

    # SMA200 slope near zero or declining.
    sma200_slope_flattening = (
        sma200_slope is not None and sma200_slope < c.SLOPE_FLATTEN_EPS
    )

    return ReversalFlags(
        macd_hist_rollover=macd_hist_rollover,
        rsi_rollover=rsi_rollover,
        return_decel=return_decel,
        obv_price_divergence=obv_price_divergence,
        sma200_slope_flattening=sma200_slope_flattening,
    )


def _obv_price_divergence(price: pd.Series, obv: pd.Series) -> bool:
    """True when price prints a new lookback high but OBV does not confirm it."""
    n = c.DIVERGENCE_LOOKBACK
    if len(price) < n or len(obv) < n:
        return False
    price_window = price.iloc[-n:].to_numpy(dtype="float64")
    obv_window = obv.iloc[-n:].to_numpy(dtype="float64")
    if np.isnan(price_window).any() or np.isnan(obv_window).any():
        return False
    price_new_high = price_window[-1] >= price_window.max()
    obv_new_high = obv_window[-1] >= obv_window.max()
    return bool(price_new_high and not obv_new_high)
