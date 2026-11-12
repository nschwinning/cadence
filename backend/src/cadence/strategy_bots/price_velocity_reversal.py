"""The Price Velocity Reversal strategy — a long-only decelerating-drop reversal signal.

Ported from the course "Algo 48 Price Velocity Reversal Algo" (its script is mislabelled
``algo 49.py``). Velocity is the latest close's change from the previous close; acceleration
is the change in velocity. When price is falling fast (velocity below −``threshold_pct``) but
the fall is slowing (acceleration above 0), a bounce is likely and the bot enters long; it
exits as soon as velocity turns positive (the course's "velocity flip"). Take-profit,
stop-loss and the drawdown kill-switch stay with the engine; the course short leg is dropped
(Cadence is long-only).

The course threshold is an absolute ₹2 move on a ₹1,000 simulated price. Cadence trades
stocks at any price, so velocity is measured as a **fraction of price** and the course value
becomes 0.2%. Stateless, pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class PriceVelocityReversalParams(StrategyParams):
    """Parameters for :class:`PriceVelocityReversalStrategy` (fraction of price per bar)."""

    threshold_pct: float = Field(default=0.002, gt=0.0, lt=1.0)

    @property
    def required_history(self) -> int:
        """Three closes: two changes give velocity and acceleration."""
        return 3


class PriceVelocityReversalStrategy:
    """Price-velocity reversal signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Enter on a sharp but decelerating drop; exit when velocity turns positive."""
        if not isinstance(params, PriceVelocityReversalParams):
            raise TypeError(
                "PriceVelocityReversalStrategy requires PriceVelocityReversalParams, got "
                f"{type(params).__name__}"
            )
        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the price velocity")

        c3, c2, c1 = (bar.close for bar in bars[-3:])
        velocity = (c1 - c2) / c2
        previous = (c2 - c3) / c3
        acceleration = velocity - previous
        summary = f"velocity {velocity:+.3%}, acceleration {acceleration:+.3%}"

        if position is not None and position.is_open:
            if velocity > 0:
                return Signal.exit(f"velocity flipped positive: {summary}")
            return Signal.hold(f"no velocity flip yet: {summary}")
        if velocity < -params.threshold_pct and acceleration > 0:
            return Signal.enter_long(f"sharp drop slowing down: {summary}")
        return Signal.hold(f"no decelerating sharp drop: {summary}")
