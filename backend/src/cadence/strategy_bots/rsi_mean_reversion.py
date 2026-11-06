"""The RSI Mean Reversion strategy — a long-only counter-trend signal.

Buys an oversold dip (Wilder-smoothed RSI below the ``oversold`` threshold while
flat) and exits as price reverts (RSI back above the ``exit_level`` threshold while
long); otherwise holds. Ported from the course "Algo 16 RSI Mean Reversion" with
the short leg dropped (Cadence is long-only) and take-profit / stop-loss / drawdown
left to the engine guardrails rather than reimplemented here. Pure and
deterministic — no I/O, no persisted state.
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


class RsiMeanReversionParams(StrategyParams):
    """Parameters for :class:`RsiMeanReversionStrategy`.

    ``oversold`` must be strictly below ``exit_level`` (otherwise the entry and exit
    bands overlap). All three default to the course values (14 / 30 / 50). Thresholds
    are on the RSI's 0–100 scale.
    """

    period: int = Field(default=14, ge=1)
    oversold: float = Field(default=30.0, ge=0.0, le=100.0)
    exit_level: float = Field(default=50.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _oversold_below_exit(self) -> RsiMeanReversionParams:
        if self.oversold >= self.exit_level:
            raise ValueError("oversold must be strictly less than exit_level")
        return self

    @property
    def required_history(self) -> int:
        """One more close than ``period`` so there are ``period`` return deltas."""
        return self.period + 1


def _wilder_rsi(closes: Sequence[float], period: int) -> float:
    """Latest Wilder-smoothed RSI of ``closes`` (caller guarantees enough history).

    Seeds the average gain/loss over the first ``period`` deltas, then Wilder-smooths
    forward over any remaining deltas. A zero average loss yields RSI 100 (no
    divide-by-zero).
    """
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class RsiMeanReversionStrategy:
    """RSI mean-reversion signal generator (satisfies the ``Strategy`` protocol)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Emit ENTER_LONG on an oversold dip, EXIT on reversion, else HOLD."""
        if not isinstance(params, RsiMeanReversionParams):
            raise TypeError(
                "RsiMeanReversionStrategy requires RsiMeanReversionParams, got "
                f"{type(params).__name__}"
            )

        closes = [bar.close for bar in bars]
        if len(closes) < params.required_history:
            return Signal.hold("insufficient history for the RSI window")

        rsi = _wilder_rsi(closes, params.period)
        holds_position = position is not None and position.is_open

        if rsi < params.oversold and not holds_position:
            return Signal.enter_long(
                f"RSI({params.period}) {rsi:.1f} below oversold {params.oversold:g}"
            )
        if rsi > params.exit_level and holds_position:
            return Signal.exit(
                f"RSI({params.period}) {rsi:.1f} reverted above "
                f"exit level {params.exit_level:g}"
            )
        return Signal.hold(f"RSI({params.period}) {rsi:.1f} within band")
