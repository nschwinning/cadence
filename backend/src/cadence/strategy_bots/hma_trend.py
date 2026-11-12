"""The HMA Trend strategy — a long-only Hull-Moving-Average trend signal.

Ported from the course "Algo 19 HMA Trend Algo" (course Algo 26 trades identically; its
news module only perturbs the simulated price feed). A fast and a slow Hull Moving Average
of the close follow price with little lag. Enter long when the fast HMA is above the slow
one **and** rising; exit on a trend reversal — the fast HMA below the slow one **and**
falling. Take-profit, stop-loss and the drawdown kill-switch stay with the engine; the
course short leg is dropped (Cadence is long-only).

This uses the **proper** Hull Moving Average: the WMA over ⌊√n⌋ of the series
2 × WMA(⌊n / 2⌋) − WMA(n). The course's ``hull_ma`` skips that final smoothing (it
averages an array of one repeated value), so its signals are faster and noisier — the
proper HMA was chosen deliberately. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class HmaTrendParams(StrategyParams):
    """Parameters for :class:`HmaTrendStrategy`. Defaults match course Algo 19."""

    fast_period: int = Field(default=9, ge=2)
    slow_period: int = Field(default=21, ge=3)

    @model_validator(mode="after")
    def _slow_above_fast(self) -> HmaTrendParams:
        if self.slow_period <= self.fast_period:
            raise ValueError("slow_period must be greater than fast_period")
        return self

    @property
    def required_history(self) -> int:
        """Bars for the slow HMA plus one more for the fast HMA's slope."""
        return self.slow_period + math.isqrt(self.slow_period)


def wma(values: Sequence[float], period: int) -> float:
    """Linearly weighted mean of the latest ``period`` values (weights 1…period, latest heaviest)."""
    window = values[-period:]
    weights = range(1, period + 1)
    return sum(w * v for w, v in zip(weights, window, strict=True)) / (period * (period + 1) / 2)


def hma(closes: Sequence[float], period: int) -> float | None:
    """Proper Hull Moving Average of ``closes`` at the latest bar (``None`` if too short)."""
    smoothing = math.isqrt(period)
    half = period // 2
    if len(closes) < period + smoothing - 1:
        return None
    raw = [
        2 * wma(closes[:end], half) - wma(closes[:end], period)
        for end in range(len(closes) - smoothing + 1, len(closes) + 1)
    ]
    return wma(raw, smoothing)


class HmaTrendStrategy:
    """Hull-Moving-Average trend signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter on a rising fast HMA above the slow one; exit on a falling cross below."""
        if not isinstance(params, HmaTrendParams):
            raise TypeError(
                f"HmaTrendStrategy requires HmaTrendParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the HMAs")

        closes = [bar.close for bar in bars]
        fast = hma(closes, params.fast_period)
        slow = hma(closes, params.slow_period)
        prev_fast = hma(closes[:-1], params.fast_period)
        if fast is None or slow is None or prev_fast is None:  # pragma: no cover - guarded
            return Signal.hold("insufficient history for the HMAs")
        slope = fast - prev_fast
        summary = f"fast HMA {fast:.4g} vs slow {slow:.4g}, slope {slope:+.3g}"

        if position is not None and position.is_open:
            if fast < slow and slope < 0:
                return Signal.exit(f"trend reversal: {summary}")
            return Signal.hold(f"no reversal: {summary}")
        if fast > slow and slope > 0:
            return Signal.enter_long(f"rising fast HMA above the slow HMA: {summary}")
        return Signal.hold(f"no rising up-trend: {summary}")
