"""The Rolling-Average Reversion strategy — a long-only buy-the-dip-below-the-mean signal.

Buys while flat when the latest close sits far enough *below* a rolling average and
exits as price reverts. Consolidates the course mean-reversion family into three
configurable axes:

* ``average_type`` — ``sma`` (mean of closes; also the course's equal-weight "VWAP",
  Algo 14), ``typical`` (mean of (high + low + close) / 3), or ``vwap`` (true
  volume-weighted average of closes, Algo 39).
* ``distance`` — ``band`` (fractional deviation below the average; Algo 5, and a zero
  band is the bare cross of Algos 14 / 39) or ``zscore`` (deviation in population
  standard deviations; Algo 4).
* ``exit_mode`` — ``revert`` (exit once the close is back at or above the exit level,
  including an overshoot above the average) or ``bracket`` (hold while in position;
  every exit is deferred to the engine's take-profit / stop-loss bracket).

The window includes the current bar, as in every course script. The course short legs
are dropped (Cadence is long-only); the course's ``abs(deviation) <= exit`` test is made
one-sided so a long that overshoots the average still exits. Sizing / TP / SL /
drawdown stay with the engine. Pure and deterministic — no I/O, no persisted state.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import Field, model_validator

from cadence.strategy_bots.adx_trend import window_directional_index
from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class RollingAverageReversionParams(StrategyParams):
    """Parameters for :class:`RollingAverageReversionStrategy`.

    ``distance`` selects which thresholds apply: ``entry_threshold`` /
    ``exit_threshold`` (fractions, 0.01 = 1%) for ``band``, ``entry_z`` / ``exit_z``
    (standard deviations) for ``zscore``. Off-mode fields simply keep their defaults.
    In ``revert`` mode the exit level must not lie below the entry level (equal is fine).
    Defaults match the course SMA band recipe (Algo 5).
    """

    average_type: Literal["sma", "typical", "vwap"] = "sma"
    window: int = Field(default=20, ge=2)
    distance: Literal["band", "zscore"] = "band"
    entry_threshold: float = Field(default=0.01, ge=0.0, lt=1.0)
    exit_threshold: float = Field(default=0.005, ge=0.0, lt=1.0)
    entry_z: float = Field(default=1.0, ge=0.0)
    exit_z: float = Field(default=0.2, ge=0.0)
    exit_mode: Literal["revert", "bracket"] = "revert"
    # Optional ADX danger exit (course Algo 15): while a position is losing, exit when
    # the directional strength over the last ``adx_lookback`` bars is above
    # ``adx_threshold`` with −DI leading +DI. Off by default (unchanged behaviour).
    adx_exit: bool = False
    adx_lookback: int = Field(default=20, ge=2)
    adx_threshold: float = Field(default=20.0, gt=0.0, lt=100.0)

    @model_validator(mode="after")
    def _exit_above_entry_when_reverting(self) -> RollingAverageReversionParams:
        if self.exit_mode != "revert":
            return self
        # Equal levels are fine: entry needs the measure strictly below the entry level and
        # the revert exit fires at or above the exit level, so no same-bar enter-and-exit.
        if self.distance == "band" and self.exit_threshold > self.entry_threshold:
            raise ValueError("exit_threshold must not exceed entry_threshold in revert mode")
        if self.distance == "zscore" and self.exit_z > self.entry_z:
            raise ValueError("exit_z must not exceed entry_z in revert mode")
        return self

    @property
    def required_history(self) -> int:
        """The rolling window (current bar included), or the ADX lookback if longer."""
        if self.adx_exit:
            return max(self.window, self.adx_lookback)
        return self.window


def _price_series(bars: Sequence[Bar], average_type: str) -> list[float]:
    """The per-bar price the average and dispersion are measured over."""
    if average_type == "typical":
        return [(bar.high + bar.low + bar.close) / 3.0 for bar in bars]
    return [bar.close for bar in bars]


def _average(bars: Sequence[Bar], series: Sequence[float], average_type: str) -> float | None:
    """Rolling average of the window, or ``None`` when undefined (zero VWAP volume)."""
    if average_type == "vwap":
        total_volume = sum(bar.volume for bar in bars)
        if total_volume <= 0.0:
            return None
        return sum(bar.close * bar.volume for bar in bars) / total_volume
    return sum(series) / len(series)


def _population_std(series: Sequence[float], mean: float) -> float:
    """Population standard deviation of ``series`` about ``mean`` (``np.std``)."""
    return math.sqrt(sum((value - mean) ** 2 for value in series) / len(series))


def _adx_danger(
    bars: Sequence[Bar], position: PositionView, params: RollingAverageReversionParams
) -> Signal | None:
    """The course Algo 15 ADX danger exit, or ``None`` when it does not fire.

    Fires only on a losing position (close below the average price) when DX over the
    last ``adx_lookback`` bars is above ``adx_threshold`` and −DI leads +DI.
    """
    close = bars[-1].close
    if close >= position.avg_price:
        return None
    reading = window_directional_index(bars[-params.adx_lookback :])
    if reading.dx > params.adx_threshold and reading.minus_di > reading.plus_di:
        return Signal.exit(
            f"ADX danger exit: close {close:g} below entry {position.avg_price:g} in a "
            f"strong downtrend (DX {reading.dx:.1f}, −DI {reading.minus_di:.1f} > "
            f"+DI {reading.plus_di:.1f})"
        )
    return None


class RollingAverageReversionStrategy:
    """Rolling-average mean-reversion signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Emit ENTER_LONG below the entry level, EXIT on reversion, else HOLD."""
        if not isinstance(params, RollingAverageReversionParams):
            raise TypeError(
                "RollingAverageReversionStrategy requires "
                f"RollingAverageReversionParams, got {type(params).__name__}"
            )

        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the rolling window")

        holds_position = position is not None and position.is_open
        if holds_position and params.adx_exit and position is not None:
            danger = _adx_danger(bars, position, params)
            if danger is not None:
                return danger
        if holds_position and params.exit_mode == "bracket":
            return Signal.hold(
                "holding; exit deferred to the take-profit / stop-loss bracket"
            )

        window = bars[-params.window :]
        series = _price_series(window, params.average_type)
        average = _average(window, series, params.average_type)
        if average is None:
            return Signal.hold("no volume in the window; VWAP undefined")

        close = bars[-1].close
        label = f"{params.window}-bar {params.average_type}"

        if params.distance == "band":
            deviation = (close - average) / average
            if not holds_position:
                if deviation < -params.entry_threshold:
                    return Signal.enter_long(
                        f"close {close:g} is {deviation:.2%} below the {label} "
                        f"{average:g} (entry {-params.entry_threshold:.2%})"
                    )
                return Signal.hold(
                    f"close {close:g} is {deviation:+.2%} from the {label} {average:g}"
                )
            if deviation >= -params.exit_threshold:
                return Signal.exit(
                    f"close {close:g} reverted to {deviation:+.2%} from the {label} "
                    f"{average:g} (exit {-params.exit_threshold:.2%})"
                )
            return Signal.hold(
                f"close {close:g} still {deviation:.2%} below the {label} {average:g}"
            )

        std = _population_std(series, sum(series) / len(series))
        if std == 0.0:
            return Signal.hold("zero dispersion in the window; z-score undefined")
        z = (close - average) / std
        if not holds_position:
            if z < -params.entry_z:
                return Signal.enter_long(
                    f"z-score {z:.2f} vs the {label} below entry {-params.entry_z:g}"
                )
            return Signal.hold(f"z-score {z:.2f} vs the {label} within band")
        if z >= -params.exit_z:
            return Signal.exit(
                f"z-score {z:.2f} vs the {label} reverted above exit {-params.exit_z:g}"
            )
        return Signal.hold(f"z-score {z:.2f} vs the {label} still below exit")
