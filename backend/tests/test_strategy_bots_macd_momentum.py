"""Unit tests for the MACD Momentum strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.macd_momentum import (
    MacdMomentumParams,
    MacdMomentumStrategy,
    macd_series,
)
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = MacdMomentumStrategy()
_PARAMS = MacdMomentumParams(fast_period=3, slow_period=6, signal_period=3)  # needs 21 bars


def _bars(closes: Sequence[float]) -> list[Bar]:
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1_000.0,
        )
        for i, c in enumerate(closes)
    ]


def _first(closes: list[float], predicate) -> int:  # type: ignore[no-untyped-def]
    """Index (in ``closes``) of the first replayed bar ≥ required history matching ``predicate``."""
    points = macd_series(closes, 3, 6, 3)
    offset = 6 - 1  # points[0] is the seed at close index slow − 1
    for k in range(1, len(points)):
        index = k + offset
        if index + 1 >= _PARAMS.required_history and predicate(points[k - 1], points[k]):
            return index
    raise AssertionError("no matching bar in the series")


def _crossed_up(prev, cur) -> bool:  # type: ignore[no-untyped-def]
    return prev.macd <= prev.signal and cur.macd > cur.signal


def test_replay_matches_a_hand_computed_series() -> None:
    points = macd_series([1, 2, 3, 4], fast=2, slow=3, signal=2)

    assert [(p.macd, p.signal) for p in points] == [
        (pytest.approx(0.5), pytest.approx(0.5)),
        (pytest.approx(0.5), pytest.approx(0.5)),
    ]
    assert macd_series([1, 2], fast=2, slow=3, signal=2) == []


def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.MACD_MOMENTUM)
    assert registration.display_name == "MACD Momentum"
    assert registration.params_schema is MacdMomentumParams


def test_params_defaults_and_validation() -> None:
    params = MacdMomentumParams()
    assert (params.fast_period, params.slow_period, params.signal_period) == (12, 26, 9)
    assert params.required_history == 87
    for bad in (
        {"fast_period": 26, "slow_period": 26},
        {"fast_period": 1},
        {"signal_period": 1},
        {"fast": 3},
    ):
        with pytest.raises(ValidationError):
            MacdMomentumParams.model_validate(bad)


def test_bullish_cross_above_zero_enters() -> None:
    # Rising, a dip that pulls MACD under its signal, then a renewed rise above zero.
    closes = [100 + i for i in range(25)] + [123, 121, 120] + [122 + 3 * i for i in range(10)]
    index = _first(closes, lambda p, c: _crossed_up(p, c) and c.macd > 0)

    signal = _STRATEGY.evaluate(_bars(closes[: index + 1]), None, _PARAMS)

    assert signal.action is SignalAction.ENTER_LONG


def test_bullish_cross_below_zero_holds() -> None:
    # Falling, then a bounce: MACD crosses its signal while still below zero.
    closes = [200 - 2 * i for i in range(30)] + [141 + 0.5 * i for i in range(6)]
    index = _first(closes, lambda p, c: _crossed_up(p, c) and c.macd < 0)

    signal = _STRATEGY.evaluate(_bars(closes[: index + 1]), None, _PARAMS)

    assert signal.action is SignalAction.HOLD
    assert "below zero" in signal.reason


def test_no_cross_holds() -> None:
    closes = [100 + 0.05 * i * i for i in range(40)]  # accelerating: MACD keeps rising
    index = _first(closes, lambda p, c: not _crossed_up(p, c) and c.macd > c.signal)

    signal = _STRATEGY.evaluate(_bars(closes[: index + 1]), None, _PARAMS)

    assert signal.action is SignalAction.HOLD


def test_holds_in_a_position_even_after_a_cross_down() -> None:
    closes = [100 + i for i in range(25)] + [100 - 3 * i for i in range(10)]

    signal = _STRATEGY.evaluate(_bars(closes), PositionView(quantity=1, avg_price=120), _PARAMS)

    assert signal.action is SignalAction.HOLD
    assert "engine" in signal.reason


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars([100.0] * 20), None, _PARAMS).action is SignalAction.HOLD


def test_never_signals_a_short() -> None:
    closes = [200 - 2 * i for i in range(60)]
    for end in range(21, len(closes) + 1):
        action = _STRATEGY.evaluate(_bars(closes[:end]), None, _PARAMS).action
        assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
