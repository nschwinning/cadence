"""Pure pandas indicator series shared by the AI-portfolio gate and the strategy bots.

One implementation of the moving-average, MACD, Wilder RSI, rate-of-change and
on-balance-volume series, so :mod:`cadence.technical_indicators.compute` (daily bars,
the AI-portfolio trend gate) and the Trend Confirmation strategy bot (intraday bars)
cannot drift apart. Every window is strictly backward-looking; warm-up yields ``NaN``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def sma(price: pd.Series, n: int) -> pd.Series:
    """Simple moving average over ``n`` bars (``NaN`` until ``n`` are available)."""
    return price.rolling(n).mean()


def ema(price: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (``adjust=False``, ``NaN`` until ``span`` bars)."""
    return price.ewm(span=span, adjust=False, min_periods=span).mean()


@dataclass(frozen=True)
class Macd:
    """MACD line, signal line and histogram series."""

    line: pd.Series
    signal: pd.Series
    histogram: pd.Series


def macd(price: pd.Series, fast: int, slow: int, signal: int) -> Macd:
    """MACD from fast / slow EMAs and an EMA signal line."""
    line = ema(price, fast) - ema(price, slow)
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return Macd(line=line, signal=signal_line, histogram=line - signal_line)


def wilder(series: pd.Series, n: int) -> pd.Series:
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


def rsi(price: pd.Series, n: int) -> pd.Series:
    """Wilder-smoothed RSI (100 with no losses; NaN with neither gains nor losses)."""
    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder(gain, n)
    avg_loss = wilder(loss, n)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_loss != 0.0, other=100.0)
    out = out.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), other=np.nan)
    return out.where(~avg_gain.isna())


def roc(price: pd.Series, n: int) -> pd.Series:
    """Rate of change over ``n`` bars, as a fraction."""
    return price / price.shift(n) - 1.0


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-balance volume: cumulative volume signed by the close's direction."""
    return (np.sign(close.diff()).fillna(0.0) * volume).cumsum()


def change(series: pd.Series, n: int) -> pd.Series:
    """Change of ``series`` over ``n`` bars (e.g. the OBV change)."""
    return series - series.shift(n)
