"""Unit tests for the Price Velocity Reversal strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.price_velocity_reversal import (
    PriceVelocityReversalParams,
    PriceVelocityReversalStrategy,
)
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = PriceVelocityReversalStrategy()
_PARAMS = PriceVelocityReversalParams()  # 0.2%
_LONG = PositionView(quantity=10, avg_price=100.0)


def _bars(closes: Sequence[float]) -> list[Bar]:
    return [
        Bar(timestamp=_START + timedelta(minutes=5 * i), open=c, high=c, low=c, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.PRICE_VELOCITY_REVERSAL)
    assert registration.display_name == "Price Velocity Reversal"
    assert registration.params_schema is PriceVelocityReversalParams


def test_params_defaults_and_validation() -> None:
    assert (_PARAMS.threshold_pct, _PARAMS.required_history) == (0.002, 3)
    for bad in ({"threshold_pct": 0}, {"threshold_pct": 1}, {"threshold": 0.01}):
        with pytest.raises(ValidationError):
            PriceVelocityReversalParams.model_validate(bad)


def test_decelerating_sharp_drop_enters() -> None:
    # −1.0% then −0.5%: falling more than 0.2% but by less than the bar before.
    assert _STRATEGY.evaluate(_bars([100, 99, 98.505]), None, _PARAMS).action is (
        SignalAction.ENTER_LONG
    )


def test_accelerating_drop_holds() -> None:
    # −0.5% then −1.0%: still speeding up.
    assert _STRATEGY.evaluate(_bars([100, 99.5, 98.505]), None, _PARAMS).action is (
        SignalAction.HOLD
    )


def test_small_drop_holds() -> None:
    # −1.0% then −0.1%: decelerating but below the 0.2% threshold.
    assert _STRATEGY.evaluate(_bars([100, 99, 98.901]), None, _PARAMS).action is SignalAction.HOLD


def test_threshold_is_price_independent() -> None:
    for scale in (0.1, 1, 10):
        closes = [100 * scale, 99 * scale, 98.505 * scale]
        assert _STRATEGY.evaluate(_bars(closes), None, _PARAMS).action is SignalAction.ENTER_LONG


def test_velocity_flip_exits() -> None:
    signal = _STRATEGY.evaluate(_bars([100, 99, 99.2]), _LONG, _PARAMS)

    assert signal.action is SignalAction.EXIT
    assert "flipped positive" in signal.reason


def test_flat_or_falling_bar_holds_the_position() -> None:
    assert _STRATEGY.evaluate(_bars([100, 99, 99]), _LONG, _PARAMS).action is SignalAction.HOLD
    assert _STRATEGY.evaluate(_bars([100, 99, 98]), _LONG, _PARAMS).action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars([100, 99]), None, _PARAMS).action is SignalAction.HOLD


def test_never_signals_a_short() -> None:
    for closes in ([100, 101, 103], [100, 103, 104], [100, 99, 98.505]):
        action = _STRATEGY.evaluate(_bars(closes), None, _PARAMS).action
        assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
