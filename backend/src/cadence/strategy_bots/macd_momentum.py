"""The MACD Momentum strategy — a long-only EMA-difference momentum signal.

Ported from the course "Algo 10 MACD Momentum Algo". Fast and slow EMAs of the close
give MACD = fast − slow; the signal line is an EMA of MACD. Enter long when MACD crosses
above its signal line on the latest bar while MACD is above zero (momentum confirmed on
the bullish side). While holding, every exit is left to the engine's take-profit /
stop-loss bracket and drawdown kill-switch — the course exits only that way. The short
leg is dropped (Cadence is long-only).

The EMAs carry state, so they are replayed over the closes provided, oldest first. Like
the course, they start from simple means: the slow EMA from the mean of the first
``slow_period`` closes, the fast EMA from the mean of the last ``fast_period`` of those,
and the signal line from that first MACD. The course seeds after a 50-price warm-up;
seeding at ``slow_period`` and replaying a fixed span lets the EMAs converge so the seed
point does not change the signals. Pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class MacdMomentumParams(StrategyParams):
    """Parameters for :class:`MacdMomentumStrategy`. Defaults match course Algo 10."""

    fast_period: int = Field(default=12, ge=2)
    slow_period: int = Field(default=26, ge=3)
    signal_period: int = Field(default=9, ge=2)

    @model_validator(mode="after")
    def _slow_above_fast(self) -> MacdMomentumParams:
        if self.slow_period <= self.fast_period:
            raise ValueError("slow_period must be greater than fast_period")
        return self

    @property
    def required_history(self) -> int:
        """Seed window plus enough replayed bars for the EMAs and signal line to settle."""
        return 3 * self.slow_period + self.signal_period


@dataclass(frozen=True)
class MacdPoint:
    """MACD and its signal line after one close."""

    macd: float
    signal: float


def _alpha(period: int) -> float:
    return 2.0 / (period + 1.0)


def macd_series(closes: Sequence[float], fast: int, slow: int, signal: int) -> list[MacdPoint]:
    """Replay the course MACD over ``closes``: one point per close from the seed on."""
    if len(closes) < slow:
        return []
    seed = closes[:slow]
    ema_slow = sum(seed) / slow
    ema_fast = sum(seed[-fast:]) / fast
    macd = ema_fast - ema_slow
    signal_line = macd
    points = [MacdPoint(macd=macd, signal=signal_line)]
    a_fast, a_slow, a_signal = _alpha(fast), _alpha(slow), _alpha(signal)
    for price in closes[slow:]:
        ema_fast = price * a_fast + ema_fast * (1 - a_fast)
        ema_slow = price * a_slow + ema_slow * (1 - a_slow)
        macd = ema_fast - ema_slow
        signal_line = macd * a_signal + signal_line * (1 - a_signal)
        points.append(MacdPoint(macd=macd, signal=signal_line))
    return points


class MacdMomentumStrategy:
    """MACD momentum signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter on a bullish MACD cross above zero; hold while in position."""
        if not isinstance(params, MacdMomentumParams):
            raise TypeError(
                f"MacdMomentumStrategy requires MacdMomentumParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the MACD")
        if position is not None and position.is_open:
            return Signal.hold("MACD holds while in position; exit deferred to the engine")

        points = macd_series(
            [bar.close for bar in bars],
            params.fast_period,
            params.slow_period,
            params.signal_period,
        )
        prev, latest = points[-2], points[-1]
        crossed_up = prev.macd <= prev.signal and latest.macd > latest.signal
        summary = f"MACD {latest.macd:.4g} vs signal {latest.signal:.4g}"
        if crossed_up and latest.macd > 0:
            return Signal.enter_long(f"bullish MACD cross above zero: {summary}")
        if crossed_up:
            return Signal.hold(f"bullish MACD cross below zero: {summary}")
        return Signal.hold(f"no bullish MACD cross: {summary}")
