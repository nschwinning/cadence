"""The Donchian Range Breakout strategy — a long-only channel-breakout signal.

Enters long when the latest close breaks *above* a Donchian high channel and exposes
two versions of the same indicator, selected by the ``version`` parameter:

* **Turtle rolling channel** (ported from the course "Algo 25 Turtle Breakout"):
  enter on a break above the highest high of the previous ``entry_period`` bars,
  exit on a break below the lowest low of the previous ``exit_period`` bars.
* **Locked channel** (folds "Algo 7 TrendLock" + "Algo 8 Smart Range Breakout"):
  enter on a break above the highest high of the previous ``channel_period`` bars,
  optionally padded outward by ``atr_padding_mult × ATR`` (a false-breakout buffer;
  padding ``0`` is the raw channel). While in a position it holds — all exits are
  deferred to the engine's take-profit / stop-loss bracket and drawdown kill-switch,
  faithfully reproducing the course's "locked while in a trade" behaviour without
  any cross-tick state.

The channel is always measured over the bars *preceding* the current bar (the
current bar is excluded) so a close can actually break out of it. The course short
legs are dropped (Cadence is long-only) and position sizing / TP / SL / drawdown are
left to the engine guardrails rather than reimplemented here. Pure and
deterministic — no I/O, no persisted state.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import Field, model_validator

from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    Signal,
    StrategyParams,
)


class DonchianBreakoutParams(StrategyParams):
    """Parameters for :class:`DonchianBreakoutStrategy`.

    ``version`` selects the variant. The Turtle version uses ``entry_period`` /
    ``exit_period`` (``exit_period`` strictly below ``entry_period``); the Locked
    version uses ``channel_period`` / ``atr_padding_mult``. The off-version fields
    simply keep their defaults. Defaults match the course values.
    """

    version: Literal["turtle", "locked"] = "turtle"
    entry_period: int = Field(default=20, ge=2)
    exit_period: int = Field(default=10, ge=1)
    channel_period: int = Field(default=20, ge=2)
    atr_padding_mult: float = Field(default=0.5, ge=0.0)

    @model_validator(mode="after")
    def _exit_below_entry(self) -> DonchianBreakoutParams:
        if self.exit_period >= self.entry_period:
            raise ValueError("exit_period must be strictly less than entry_period")
        return self

    @property
    def required_history(self) -> int:
        """One more bar than the channel lookback, so the channel excludes the
        current bar. Branches on the active version's lookback window."""
        if self.version == "turtle":
            return self.entry_period + 1
        return self.channel_period + 1


def _highest_high(bars: Sequence[Bar]) -> float:
    """Highest high across ``bars`` (caller guarantees a non-empty window)."""
    return max(bar.high for bar in bars)


def _lowest_low(bars: Sequence[Bar]) -> float:
    """Lowest low across ``bars`` (caller guarantees a non-empty window)."""
    return min(bar.low for bar in bars)


def _mean_abs_close_change(bars: Sequence[Bar]) -> float:
    """Simple ATR proxy: mean absolute successive close change over ``bars``.

    Mirrors the course ``calc_atr`` (a mean of close-to-close moves rather than a
    true-range ATR). Returns ``0.0`` for a window with fewer than two bars.
    """
    closes = [bar.close for bar in bars]
    if len(closes) < 2:
        return 0.0
    diffs = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    return sum(diffs) / len(diffs)


class DonchianBreakoutStrategy:
    """Donchian channel-breakout signal generator (satisfies ``Strategy``)."""

    def evaluate(
        self,
        bars: Sequence[Bar],
        position: PositionView | None,
        params: StrategyParams,
    ) -> Signal:
        """Emit ENTER_LONG on an upward channel breakout; exits depend on version."""
        if not isinstance(params, DonchianBreakoutParams):
            raise TypeError(
                "DonchianBreakoutStrategy requires DonchianBreakoutParams, got "
                f"{type(params).__name__}"
            )

        if len(bars) < params.required_history:
            return Signal.hold("insufficient history for the Donchian channel")

        close = bars[-1].close
        holds_position = position is not None and position.is_open

        if params.version == "turtle":
            return self._evaluate_turtle(bars, close, holds_position, params)
        return self._evaluate_locked(bars, close, holds_position, params)

    def _evaluate_turtle(
        self,
        bars: Sequence[Bar],
        close: float,
        holds_position: bool,
        params: DonchianBreakoutParams,
    ) -> Signal:
        """Rolling channel: enter above the entry high, exit below the exit low."""
        if not holds_position:
            window = bars[-(params.entry_period + 1) : -1]
            upper = _highest_high(window)
            if close > upper:
                return Signal.enter_long(
                    f"close {close:g} broke above the "
                    f"{params.entry_period}-bar high {upper:g}"
                )
            return Signal.hold(
                f"close {close:g} at or below the "
                f"{params.entry_period}-bar high {upper:g}"
            )

        window = bars[-(params.exit_period + 1) : -1]
        lower = _lowest_low(window)
        if close < lower:
            return Signal.exit(
                f"close {close:g} broke below the "
                f"{params.exit_period}-bar low {lower:g}"
            )
        return Signal.hold(
            f"close {close:g} at or above the "
            f"{params.exit_period}-bar low {lower:g}"
        )

    def _evaluate_locked(
        self,
        bars: Sequence[Bar],
        close: float,
        holds_position: bool,
        params: DonchianBreakoutParams,
    ) -> Signal:
        """Locked channel: enter above the padded high; hold in position (engine exits)."""
        if holds_position:
            return Signal.hold(
                "locked channel holds while in position; exit deferred to the engine"
            )

        window = bars[-(params.channel_period + 1) : -1]
        upper = _highest_high(window) + params.atr_padding_mult * _mean_abs_close_change(
            window
        )
        if close > upper:
            return Signal.enter_long(
                f"close {close:g} broke above the padded "
                f"{params.channel_period}-bar high {upper:g}"
            )
        return Signal.hold(
            f"close {close:g} at or below the padded "
            f"{params.channel_period}-bar high {upper:g}"
        )
