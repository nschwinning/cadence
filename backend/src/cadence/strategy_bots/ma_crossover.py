"""The MA Crossover strategy — the single strategy shipped in v1.

A classic dual-simple-moving-average crossover: when the fast SMA crosses *above*
the slow SMA it signals ``ENTER_LONG``; when it crosses back *below* it signals
``EXIT``; otherwise ``HOLD``. With fewer bars than the slow window (plus one, to
see the prior cross state) it holds rather than erroring. Pure and deterministic —
no I/O, no persisted state.
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


class MACrossoverParams(StrategyParams):
    """Parameters for :class:`MACrossoverStrategy`.

    ``fast_period`` must be strictly shorter than ``slow_period`` (otherwise the
    two averages never genuinely cross). Both default to the conventional 20/50.
    """

    fast_period: int = Field(default=20, ge=1)
    slow_period: int = Field(default=50, ge=2)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> MACrossoverParams:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be strictly less than slow_period")
        return self

    @property
    def required_history(self) -> int:
        """Slow window plus one bar, so the previous cross state is visible."""
        return self.slow_period + 1


def _sma(values: Sequence[float], period: int) -> float:
    """Simple moving average over the final ``period`` values of ``values``."""
    window = values[-period:]
    return sum(window) / len(window)


class MACrossoverStrategy:
    """Dual-SMA crossover signal generator (satisfies the ``Strategy`` protocol)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Emit ENTER_LONG on an up-cross, EXIT on a down-cross, else HOLD."""
        if not isinstance(params, MACrossoverParams):
            raise TypeError(
                "MACrossoverStrategy requires MACrossoverParams, got "
                f"{type(params).__name__}"
            )

        closes = [bar.close for bar in bars]
        # Need slow_period bars ending at the previous bar (to know the prior
        # cross state) plus the latest bar: slow_period + 1 closes in total.
        if len(closes) < params.slow_period + 1:
            return Signal.hold("insufficient history for the slow moving average")

        prev_fast = _sma(closes[:-1], params.fast_period)
        prev_slow = _sma(closes[:-1], params.slow_period)
        curr_fast = _sma(closes, params.fast_period)
        curr_slow = _sma(closes, params.slow_period)

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow
        holds_position = position is not None and position.is_open

        if crossed_up and not holds_position:
            return Signal.enter_long(
                f"fast SMA({params.fast_period}) crossed above "
                f"slow SMA({params.slow_period})"
            )
        if crossed_down and holds_position:
            return Signal.exit(
                f"fast SMA({params.fast_period}) crossed below "
                f"slow SMA({params.slow_period})"
            )
        return Signal.hold("no crossover")
