"""Unit tests for the MA Ribbon strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.ma_ribbon import MaRibbonParams, MaRibbonStrategy
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = MaRibbonStrategy()
_PARAMS = MaRibbonParams(fast_period=2, mid_period=3, slow_period=5)


def _bars(closes: Sequence[float]) -> list[Bar]:
    return [
        Bar(timestamp=_START + timedelta(minutes=5 * i), open=c, high=c, low=c, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.MA_RIBBON)
    assert registration.display_name == "MA Ribbon"
    assert registration.params_schema is MaRibbonParams


def test_params_defaults_and_validation() -> None:
    params = MaRibbonParams()
    assert (params.fast_period, params.mid_period, params.slow_period) == (5, 10, 20)
    assert params.required_history == 20
    for bad in (
        {"fast_period": 10, "mid_period": 10, "slow_period": 20},
        {"fast_period": 5, "mid_period": 20, "slow_period": 20},
        {"fast_period": 5, "mid_period": 30, "slow_period": 20},
        {"fast": 5},
    ):
        with pytest.raises(ValidationError):
            MaRibbonParams.model_validate(bad)


def test_upward_alignment_enters() -> None:
    # fast (last 2) 104.5 > mid (last 3) 104 > slow (last 5) 103
    assert _STRATEGY.evaluate(_bars([101, 102, 103, 104, 105]), None, _PARAMS).action is (
        SignalAction.ENTER_LONG
    )


def test_partial_alignment_holds() -> None:
    # fast 105.5 > mid 104.33 but mid ≤ slow 104.6 (the early high drags the slow SMA)
    closes = [110, 100, 102, 106, 105]
    signal = _STRATEGY.evaluate(_bars(closes), None, _PARAMS)

    assert signal.action is SignalAction.HOLD
    assert "not aligned" in signal.reason


def test_falling_ribbon_holds_flat() -> None:
    assert _STRATEGY.evaluate(_bars([105, 104, 103, 102, 101]), None, _PARAMS).action is (
        SignalAction.HOLD
    )


def test_holds_in_a_position_even_after_a_down_turn() -> None:
    signal = _STRATEGY.evaluate(
        _bars([105, 104, 103, 102, 101]), PositionView(quantity=1, avg_price=105), _PARAMS
    )

    assert signal.action is SignalAction.HOLD
    assert "engine" in signal.reason


def test_insufficient_history_holds() -> None:
    assert (
        _STRATEGY.evaluate(_bars([101, 102, 103, 104]), None, _PARAMS).action is SignalAction.HOLD
    )


def test_never_signals_a_short() -> None:
    for closes in ([105, 104, 103, 102, 101], [101, 102, 103, 104, 105], [100] * 5):
        action = _STRATEGY.evaluate(_bars(closes), None, _PARAMS).action
        assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
