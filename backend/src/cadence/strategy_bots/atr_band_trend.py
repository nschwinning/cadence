"""The ATR-Band Trend strategy — a long-only "midline ± k·ATR" trend signal.

Two versions of the same volatility-band family, selected by the ``version`` parameter:

* **SuperTrend** (ported from the course "Algo 9 SuperTrend Algo"): over each rolling
  window of ``window`` closes, bands sit at the window's mid-range ± ``atr_mult × ATR``
  and only tighten while the trend persists (the upper band never rises in an up-trend,
  the lower band never falls in a down-trend). The trend is up while the close stays
  above the previous SuperTrend line, which is the lower band in an up-trend and the
  upper band in a down-trend. Enter long when the trend is up and the close is above the
  line; while holding, every exit is left to the engine's take-profit / stop-loss
  bracket and drawdown kill-switch — the course exits only that way.
* **Keltner** (ported from "Algo 21 Keltner Volatility Breakout"): bands at
  SMA(``window``) ± ``atr_mult × ATR``. Enter long on a close above the upper band; exit
  when the close falls back below the SMA (``exit_on_midline``).

Both read closes only, like the course's single price stream, and use its ATR proxy (the
mean absolute close-to-close change). SuperTrend is path-dependent, so it is replayed over
the bars provided, oldest first — deterministic for the same bars, with no persisted
state. Course short legs (and Keltner's flip to short) are dropped: Cadence is long-only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)

#: SuperTrend replays this many windows so its band ratchet has settled by the last bar.
_SUPERTREND_HISTORY_WINDOWS = 3


class AtrBandTrendParams(StrategyParams):
    """Parameters for :class:`AtrBandTrendStrategy`.

    ``version`` selects the variant; ``exit_on_midline`` applies to Keltner only.
    Defaults match the SuperTrend course values (Algo 9).
    """

    version: Literal["supertrend", "keltner"] = "supertrend"
    window: int = Field(default=20, ge=2)
    atr_mult: float = Field(default=3.0, gt=0.0)
    exit_on_midline: bool = True

    @property
    def required_history(self) -> int:
        """SuperTrend replays several windows; Keltner needs one window of closes."""
        if self.version == "supertrend":
            return self.window * _SUPERTREND_HISTORY_WINDOWS
        return self.window


def mean_abs_close_change(closes: Sequence[float]) -> float:
    """Course ATR proxy: mean absolute change between consecutive closes (0 if < 2)."""
    if len(closes) < 2:
        return 0.0
    return sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) / (len(closes) - 1)


@dataclass(frozen=True)
class SuperTrendState:
    """The SuperTrend after the latest bar: trend direction, line and bands."""

    trend: Literal["up", "down"]
    line: float
    upper: float
    lower: float


def supertrend(closes: Sequence[float], window: int, atr_mult: float) -> SuperTrendState | None:
    """Replay the course SuperTrend over ``closes`` (oldest first); ``None`` if too short."""
    if len(closes) < window:
        return None
    trend: Literal["up", "down"] | None = None
    prev_upper: float | None = None
    prev_lower: float | None = None
    prev_line: float | None = None
    state: SuperTrendState | None = None
    for end in range(window, len(closes) + 1):
        recent = closes[end - window : end]
        close = recent[-1]
        mid = (max(recent) + min(recent)) / 2
        atr = mean_abs_close_change(recent)
        upper_basic = mid + atr_mult * atr
        lower_basic = mid - atr_mult * atr
        upper = (
            min(upper_basic, prev_upper)
            if trend == "up" and prev_upper is not None
            else upper_basic
        )
        lower = (
            max(lower_basic, prev_lower)
            if trend == "down" and prev_lower is not None
            else lower_basic
        )
        if prev_line is None:
            trend = "up" if close > mid else "down"
            line = mid
        else:
            trend = "up" if close > prev_line else "down"
            line = lower if trend == "up" else upper
        prev_upper, prev_lower, prev_line = upper, lower, line
        state = SuperTrendState(trend=trend, line=line, upper=upper, lower=lower)
    return state


class AtrBandTrendStrategy:
    """ATR-band trend signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """SuperTrend or Keltner entry; exits per version (see the module docstring)."""
        if not isinstance(params, AtrBandTrendParams):
            raise TypeError(
                f"AtrBandTrendStrategy requires AtrBandTrendParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the ATR bands")

        closes = [bar.close for bar in bars]
        holds_position = position is not None and position.is_open
        if params.version == "supertrend":
            return self._evaluate_supertrend(closes, holds_position, params)
        return self._evaluate_keltner(closes, holds_position, params)

    def _evaluate_supertrend(
        self, closes: list[float], holds_position: bool, params: AtrBandTrendParams
    ) -> Signal:
        if holds_position:
            return Signal.hold("SuperTrend holds while in position; exit deferred to the engine")
        state = supertrend(closes, params.window, params.atr_mult)
        if state is None:  # pragma: no cover - guarded by required_history
            return Signal.hold("insufficient history for the SuperTrend")
        close = closes[-1]
        if state.trend == "up" and close > state.line:
            return Signal.enter_long(
                f"trend up and close {close:g} above the SuperTrend {state.line:g}"
            )
        return Signal.hold(f"trend {state.trend}, close {close:g} vs SuperTrend {state.line:g}")

    def _evaluate_keltner(
        self, closes: list[float], holds_position: bool, params: AtrBandTrendParams
    ) -> Signal:
        recent = closes[-params.window :]
        close = recent[-1]
        mid = sum(recent) / len(recent)
        atr = mean_abs_close_change(recent)
        upper = mid + params.atr_mult * atr
        if not holds_position:
            if close > upper:
                return Signal.enter_long(
                    f"close {close:g} broke above the Keltner upper band {upper:g}"
                )
            return Signal.hold(f"close {close:g} at or below the upper band {upper:g}")
        if params.exit_on_midline and close < mid:
            return Signal.exit(f"close {close:g} fell below the {params.window}-bar SMA {mid:g}")
        return Signal.hold(f"close {close:g} holding above the SMA {mid:g}")
