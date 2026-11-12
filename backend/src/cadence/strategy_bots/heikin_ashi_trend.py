"""The Heikin-Ashi Trend strategy — a long-only trend signal on Heikin-Ashi candles.

Ported from the course "Algo 11 Heikin-Ashi Trend Catcher", with "Algo 37 Heikin-Ashi Trend
+ Volume Momentum Engine" as its optional volume filter. Heikin-Ashi candles smooth bar
noise: each candle's close is the mean of its bar's open, high, low and close, and its open
is the mean of the previous Heikin-Ashi candle's open and close (the first one uses its bar's
(open + close) / 2). A candle is green when its close is above its open.

* Without the filter (Algo 11): enter long on a green candle, exit on a red one.
* With the filter (Algo 37): enter only on a green candle whose bar volume is above the mean
  of the latest ``volume_window`` bars (current bar included); exit on a red candle or when
  volume fades to or below that mean.

The Heikin-Ashi open is path-dependent, so the candles are replayed over a fixed span of
bars, oldest first. The course short legs are dropped (Cadence is long-only); take-profit,
stop-loss and the drawdown kill-switch stay with the engine. Pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)

#: Candles replayed to settle the path-dependent Heikin-Ashi open (the course warm-up).
HA_REPLAY_BARS = 10


class HeikinAshiTrendParams(StrategyParams):
    """Parameters for :class:`HeikinAshiTrendStrategy`. Defaults match course Algo 11."""

    volume_filter: bool = False
    volume_window: int = Field(default=20, ge=2)

    @property
    def required_history(self) -> int:
        """The Heikin-Ashi replay span, or the volume window if longer and in use."""
        if self.volume_filter:
            return max(HA_REPLAY_BARS, self.volume_window)
        return HA_REPLAY_BARS


@dataclass(frozen=True)
class HeikinAshiCandle:
    """One Heikin-Ashi candle."""

    open: float
    high: float
    low: float
    close: float

    @property
    def green(self) -> bool:
        return self.close > self.open


def heikin_ashi(bars: Sequence[Bar]) -> list[HeikinAshiCandle]:
    """Heikin-Ashi candles for ``bars``, oldest first (course ``heikin_ashi_candle``)."""
    candles: list[HeikinAshiCandle] = []
    prev: HeikinAshiCandle | None = None
    for bar in bars:
        close = (bar.open + bar.high + bar.low + bar.close) / 4.0
        open_ = (bar.open + bar.close) / 2.0 if prev is None else (prev.open + prev.close) / 2.0
        candle = HeikinAshiCandle(
            open=open_,
            high=max(bar.high, open_, close),
            low=min(bar.low, open_, close),
            close=close,
        )
        candles.append(candle)
        prev = candle
    return candles


def strong_volume(bars: Sequence[Bar], window: int) -> bool:
    """Latest bar volume strictly above the mean of the latest ``window`` bars (0 mean → no)."""
    recent = bars[-window:]
    mean = sum(bar.volume for bar in recent) / len(recent)
    return mean > 0 and bars[-1].volume > mean


class HeikinAshiTrendStrategy:
    """Heikin-Ashi trend signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Trade the latest Heikin-Ashi candle's colour, optionally confirmed by volume."""
        if not isinstance(params, HeikinAshiTrendParams):
            raise TypeError(
                "HeikinAshiTrendStrategy requires HeikinAshiTrendParams, got "
                f"{type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the Heikin-Ashi candles")

        span = bars[-params.required_history :]
        candle = heikin_ashi(span[-HA_REPLAY_BARS:])[-1]
        colour = "green" if candle.green else "red"
        strong = strong_volume(span, params.volume_window) if params.volume_filter else True
        holds_position = position is not None and position.is_open

        if holds_position:
            if not candle.green:
                return Signal.exit("Heikin-Ashi candle turned red")
            if not strong:
                return Signal.exit("volume faded to or below its recent average")
            return Signal.hold(f"Heikin-Ashi candle still {colour}")
        if candle.green and strong:
            confirmation = " with above-average volume" if params.volume_filter else ""
            return Signal.enter_long(f"green Heikin-Ashi candle{confirmation}")
        if candle.green:
            return Signal.hold("green Heikin-Ashi candle but volume not above average")
        return Signal.hold("red Heikin-Ashi candle")
