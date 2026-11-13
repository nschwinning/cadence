"""The Volume Breakout strategy — long-only, volume-confirmed signals.

Three versions of the volume family, selected by the ``version`` parameter:

* **Spike** (ported from the course "Algo 34 Volume Spike – Simple vs Multiplier Method"):
  enter long when the close breaks above the highest close of the prior ``lookback − 1``
  bars while the bar's volume exceeds ``spike_multiplier`` × the average volume of the
  latest ``volume_window`` bars. The course only prints signals; its "short breakout"
  (a close below the prior low with a volume spike) is the long exit here.
* **VROC** (ported from "Algo 46 Volume Rate of Change"): VROC is the latest volume's
  percentage change from the volume ``vroc_lookback`` bars earlier. A bar *primes* when VROC
  exceeds ``vroc_threshold`` and its ``range_lookback``-bar close range is tight (or VROC
  exceeds ``vroc_surge``). Enter on the first close above a priming bar's range high, if the
  priming is at most ``prime_window`` bars old; exit when VROC turns negative. The course
  remembers a priming until it trades; Cadence is stateless, so it looks back a bounded
  window and uses the most recent priming.
* **Chaikin** (ported from "Algo 45 Chaikin Oscillator Algo"): the accumulation/distribution
  line from real high / low / close / volume (the course fakes the high and low at random);
  the oscillator is EMA(``chaikin_fast``) − EMA(``chaikin_slow``) of it, using proper
  converged EMAs (the course truncates them to the last few values). Enter when the
  oscillator crosses above zero; exit when it falls below zero.

Course short legs are dropped (Cadence is long-only); take-profit, stop-loss and the drawdown
kill-switch stay with the engine. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)
from cadence.technical_indicators import series

#: The Chaikin EMAs are replayed over this many slow spans so they have converged.
_CHAIKIN_HISTORY_SPANS = 3


class VolumeBreakoutParams(StrategyParams):
    """Parameters for :class:`VolumeBreakoutStrategy`.

    ``version`` selects the variant; each version reads only its own fields. Defaults match
    the course values (Algo 34 b, Algo 46, Algo 45).
    """

    version: Literal["spike", "vroc", "chaikin"] = "spike"
    lookback: int = Field(default=30, ge=3)
    volume_window: int = Field(default=20, ge=1)
    spike_multiplier: float = Field(default=1.1, gt=0.0)
    vroc_lookback: int = Field(default=5, ge=1)
    range_lookback: int = Field(default=5, ge=2)
    vroc_threshold: float = 40.0
    vroc_surge: float = 70.0
    tight_range_pct: float = Field(default=0.006, gt=0.0, lt=1.0)
    prime_window: int = Field(default=10, ge=1)
    chaikin_fast: int = Field(default=3, ge=1)
    chaikin_slow: int = Field(default=5, ge=2)

    @model_validator(mode="after")
    def _ordered(self) -> VolumeBreakoutParams:
        if self.vroc_surge < self.vroc_threshold:
            raise ValueError("vroc_surge must not be below vroc_threshold")
        if self.chaikin_fast >= self.chaikin_slow:
            raise ValueError("chaikin_fast must be less than chaikin_slow")
        return self

    @property
    def required_history(self) -> int:
        """Bars the selected version needs (see the module docstring)."""
        if self.version == "spike":
            return max(self.lookback, self.volume_window)
        if self.version == "vroc":
            return self.prime_window + max(self.vroc_lookback, self.range_lookback - 1) + 1
        return _CHAIKIN_HISTORY_SPANS * self.chaikin_slow + 1


def vroc(volumes: Sequence[float], index: int, lookback: int) -> float | None:
    """Volume rate of change (%) at ``index``; ``None`` if undefined."""
    if index - lookback < 0:
        return None
    earlier = volumes[index - lookback]
    if earlier <= 0:
        return None
    return (volumes[index] - earlier) / earlier * 100


def accumulation_distribution(bars: Sequence[Bar]) -> list[float]:
    """Running sum of money-flow volume over ``bars`` (oldest first)."""
    line: list[float] = []
    total = 0.0
    for bar in bars:
        span = bar.high - bar.low
        multiplier = ((bar.close - bar.low) - (bar.high - bar.close)) / span if span else 0.0
        total += multiplier * bar.volume
        line.append(total)
    return line


def chaikin_oscillator(bars: Sequence[Bar], fast: int, slow: int) -> pd.Series:
    """EMA(fast) − EMA(slow) of the accumulation/distribution line."""
    adl = pd.Series(accumulation_distribution(bars), dtype="float64")
    return series.ema(adl, fast) - series.ema(adl, slow)


def _defined(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


class VolumeBreakoutStrategy:
    """Volume-confirmed signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Dispatch to the selected version."""
        if not isinstance(params, VolumeBreakoutParams):
            raise TypeError(
                f"VolumeBreakoutStrategy requires VolumeBreakoutParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the volume signal")
        holding = position is not None and position.is_open
        if params.version == "spike":
            return self._spike(bars, holding, params)
        if params.version == "vroc":
            return self._vroc(bars, holding, params)
        return self._chaikin(bars, holding, params)

    @staticmethod
    def _spike(bars: Sequence[Bar], holding: bool, params: VolumeBreakoutParams) -> Signal:
        prior = [bar.close for bar in bars[-params.lookback : -1]]
        high, low = max(prior), min(prior)
        window = [bar.volume for bar in bars[-params.volume_window :]]
        average = sum(window) / len(window)
        close, volume = bars[-1].close, bars[-1].volume
        spike = volume > average * params.spike_multiplier
        summary = (
            f"close {close:g} vs prior range {low:g}–{high:g}, volume {volume:g} vs "
            f"{params.spike_multiplier:g}× average {average:.4g}"
        )
        if holding:
            if close < low and spike:
                return Signal.exit(f"volume-confirmed breakdown: {summary}")
            return Signal.hold(f"no volume-confirmed breakdown: {summary}")
        if close > high and spike:
            return Signal.enter_long(f"volume-confirmed breakout: {summary}")
        return Signal.hold(f"no volume-confirmed breakout: {summary}")

    @staticmethod
    def _vroc(bars: Sequence[Bar], holding: bool, params: VolumeBreakoutParams) -> Signal:
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        last = len(bars) - 1
        current = vroc(volumes, last, params.vroc_lookback)

        if holding:
            if current is None:
                return Signal.hold("VROC undefined (no volume on the earlier bar)")
            if current < 0:
                return Signal.exit(f"VROC reversed to {current:.1f}%")
            return Signal.hold(f"VROC {current:.1f}% still non-negative")

        for index in range(last - 1, last - 1 - params.prime_window, -1):
            surge = vroc(volumes, index, params.vroc_lookback)
            if surge is None or surge <= params.vroc_threshold:
                continue
            window = closes[index - params.range_lookback + 1 : index + 1]
            high, low = max(window), min(window)
            tight = high - low < params.tight_range_pct * closes[index]
            if not (tight or surge > params.vroc_surge):
                continue
            bars_ago = last - index
            if any(close > high for close in closes[index + 1 : last]):
                return Signal.hold(
                    f"range {low:g}–{high:g} primed {bars_ago} bars ago is already broken"
                )
            if closes[last] > high:
                return Signal.enter_long(
                    f"close {closes[last]:g} broke the range {low:g}–{high:g} primed "
                    f"{bars_ago} bars ago (VROC {surge:.1f}%)"
                )
            return Signal.hold(f"waiting for a close above {high:g} (primed {bars_ago} bars ago)")
        return Signal.hold(f"no volume priming in the last {params.prime_window} bars")

    @staticmethod
    def _chaikin(bars: Sequence[Bar], holding: bool, params: VolumeBreakoutParams) -> Signal:
        oscillator = chaikin_oscillator(bars, params.chaikin_fast, params.chaikin_slow)
        current, previous = float(oscillator.iloc[-1]), float(oscillator.iloc[-2])
        if not (_defined(current) and _defined(previous)):  # pragma: no cover - guarded
            return Signal.hold("insufficient history for the Chaikin oscillator")
        summary = f"Chaikin oscillator {previous:.4g} → {current:.4g}"
        if holding:
            if current < 0:
                return Signal.exit(f"oscillator below zero: {summary}")
            return Signal.hold(f"oscillator not below zero: {summary}")
        if previous <= 0 < current:
            return Signal.enter_long(f"oscillator crossed above zero: {summary}")
        return Signal.hold(f"no zero-line cross up: {summary}")
