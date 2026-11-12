"""The MA Ribbon strategy — a long-only three-moving-average alignment signal.

Ported from the course "Algo 18 MA Ribbon Alignment". Three simple moving averages of the
close — fast, mid and slow — form a ribbon; when they stack upward (fast above mid above
slow) the trend is confirmed on every horizon and the bot enters long. While holding, every
exit is left to the engine's take-profit / stop-loss bracket and drawdown kill-switch — the
course exits only that way. The course short leg is dropped (Cadence is long-only).
Stateless, pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class MaRibbonParams(StrategyParams):
    """Parameters for :class:`MaRibbonStrategy`. Defaults match course Algo 18."""

    fast_period: int = Field(default=5, ge=1)
    mid_period: int = Field(default=10, ge=2)
    slow_period: int = Field(default=20, ge=3)

    @model_validator(mode="after")
    def _strictly_increasing(self) -> MaRibbonParams:
        if not self.fast_period < self.mid_period < self.slow_period:
            raise ValueError("periods must increase strictly: fast < mid < slow")
        return self

    @property
    def required_history(self) -> int:
        """The slow average's window (the current bar included)."""
        return self.slow_period


def _sma(closes: Sequence[float], period: int) -> float:
    window = closes[-period:]
    return sum(window) / len(window)


class MaRibbonStrategy:
    """MA ribbon alignment signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter when the ribbon stacks upward; hold while in position."""
        if not isinstance(params, MaRibbonParams):
            raise TypeError(
                f"MaRibbonStrategy requires MaRibbonParams, got {type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the ribbon")
        if position is not None and position.is_open:
            return Signal.hold("ribbon holds while in position; exit deferred to the engine")

        closes = [bar.close for bar in bars]
        fast = _sma(closes, params.fast_period)
        mid = _sma(closes, params.mid_period)
        slow = _sma(closes, params.slow_period)
        summary = f"SMA {params.fast_period} {fast:.4g} / {params.mid_period} {mid:.4g} / {params.slow_period} {slow:.4g}"
        if fast > mid > slow:
            return Signal.enter_long(f"ribbon aligned upward: {summary}")
        return Signal.hold(f"ribbon not aligned upward: {summary}")
