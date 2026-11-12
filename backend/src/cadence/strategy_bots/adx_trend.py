"""The ADX Trend Strength strategy — a long-only directional-movement trend signal.

Ported from the course "Algo 12 ADX Trend Strength System". For every bar after the
first it measures the true range and the directional movement (+DM / −DM); over rolling
``period`` sums it derives +DI, −DI and the directional strength DX, and ADX is the mean
of the latest ``period`` DX values. The course uses **plain sums** (``np.convolve`` with
ones), not Wilder smoothing, and so does this port.

Enter long when ADX is above ``threshold`` and +DI leads −DI; exit when ADX falls back
below ``threshold``. Take-profit, stop-loss and the drawdown kill-switch stay with the
engine. The course short leg is dropped (Cadence is long-only). Pure and deterministic.

The directional-movement helpers are shared with the Rolling-Average Reversion
strategy's optional ADX danger exit (course "Algo 15 VWAP + ADX Monitoring").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


@dataclass(frozen=True)
class DirectionalMovement:
    """Per-bar true range and directional movement (one entry per bar after the first)."""

    tr: list[float]
    plus_dm: list[float]
    minus_dm: list[float]


@dataclass(frozen=True)
class DirectionalIndex:
    """+DI, −DI and DX for one summed window."""

    plus_di: float
    minus_di: float
    dx: float


def directional_movement(bars: Sequence[Bar]) -> DirectionalMovement:
    """True range, +DM and −DM for each bar after the first (course ``calc_adx``)."""
    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for prev, bar in pairwise(bars):
        up = bar.high - prev.high
        down = prev.low - bar.low
        tr.append(max(bar.high - bar.low, abs(bar.high - prev.close), abs(bar.low - prev.close)))
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    return DirectionalMovement(tr=tr, plus_dm=plus_dm, minus_dm=minus_dm)


def directional_index(tr_sum: float, plus_sum: float, minus_sum: float) -> DirectionalIndex:
    """+DI, −DI and DX from summed TR / +DM / −DM (all 0 when there is no range)."""
    if tr_sum <= 0:
        return DirectionalIndex(plus_di=0.0, minus_di=0.0, dx=0.0)
    plus_di = 100.0 * plus_sum / tr_sum
    minus_di = 100.0 * minus_sum / tr_sum
    total = plus_di + minus_di
    dx = 100.0 * abs(plus_di - minus_di) / total if total > 0 else 0.0
    return DirectionalIndex(plus_di=plus_di, minus_di=minus_di, dx=dx)


def window_directional_index(bars: Sequence[Bar]) -> DirectionalIndex:
    """+DI, −DI and DX summed over all of ``bars`` (one window)."""
    dm = directional_movement(bars)
    return directional_index(sum(dm.tr), sum(dm.plus_dm), sum(dm.minus_dm))


@dataclass(frozen=True)
class AdxReading:
    """The latest window's +DI / −DI and the ADX (mean of the latest ``period`` DX)."""

    plus_di: float
    minus_di: float
    adx: float


def adx(bars: Sequence[Bar], period: int) -> AdxReading | None:
    """Course ADX over ``bars``: rolling-sum DI/DX, ADX = mean of the last ``period`` DX."""
    dm = directional_movement(bars)
    if len(dm.tr) < period:
        return None
    readings = [
        directional_index(
            sum(dm.tr[i : i + period]),
            sum(dm.plus_dm[i : i + period]),
            sum(dm.minus_dm[i : i + period]),
        )
        for i in range(len(dm.tr) - period + 1)
    ]
    if len(readings) < period:
        return None
    latest = readings[-1]
    return AdxReading(
        plus_di=latest.plus_di,
        minus_di=latest.minus_di,
        adx=sum(r.dx for r in readings[-period:]) / period,
    )


class AdxTrendParams(StrategyParams):
    """Parameters for :class:`AdxTrendStrategy`. Defaults match course Algo 12."""

    period: int = Field(default=10, ge=2)
    threshold: float = Field(default=20.0, gt=0.0, lt=100.0)

    @property
    def required_history(self) -> int:
        """``period`` − 1 changes for the first DI window plus ``period`` DX values."""
        return 2 * self.period


class AdxTrendStrategy:
    """ADX trend-strength signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter on a strong up-trend (ADX > threshold, +DI > −DI); exit when ADX weakens."""
        if not isinstance(params, AdxTrendParams):
            raise TypeError(
                f"AdxTrendStrategy requires AdxTrendParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the ADX")
        reading = adx(bars, params.period)
        if reading is None:  # pragma: no cover - guarded by required_history
            return Signal.hold("insufficient history for the ADX")

        holds_position = position is not None and position.is_open
        summary = f"ADX {reading.adx:.1f}, +DI {reading.plus_di:.1f}, −DI {reading.minus_di:.1f}"
        if holds_position:
            if reading.adx < params.threshold:
                return Signal.exit(f"trend weakened: {summary} below {params.threshold:g}")
            return Signal.hold(f"trend still strong: {summary}")
        if reading.adx > params.threshold and reading.plus_di > reading.minus_di:
            return Signal.enter_long(f"strong up-trend: {summary}")
        return Signal.hold(f"no strong up-trend: {summary}")
