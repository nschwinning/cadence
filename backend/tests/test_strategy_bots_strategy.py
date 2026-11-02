"""Unit tests for the pure MA Crossover strategy and the strategy registry."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from cadence.strategy_bots.errors import (
    InvalidStrategyParamsError,
    UnknownStrategyError,
)
from cadence.strategy_bots.ma_crossover import (
    MACrossoverParams,
    MACrossoverStrategy,
)
from cadence.strategy_bots.registry import get_strategy, list_strategies
from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    SignalAction,
    Strategy,
)

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


def _bars(closes: Sequence[float]) -> list[Bar]:
    """Build a bar series from close prices (OHLCV flat around the close)."""
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )
        for i, close in enumerate(closes)
    ]


def test_strategy_satisfies_protocol() -> None:
    """The concrete strategy is recognised as a ``Strategy`` at runtime."""
    assert isinstance(MACrossoverStrategy(), Strategy)


def test_fast_cross_above_slow_enters_long() -> None:
    """A fresh up-cross with no position open returns ENTER_LONG."""
    params = MACrossoverParams(fast_period=2, slow_period=3)
    # Flat-then-rising closes: fast SMA is below slow, then crosses above on the
    # final bar.
    closes = [10.0, 10.0, 10.0, 10.0, 20.0]
    signal = MACrossoverStrategy().evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.ENTER_LONG
    assert signal.reason


def test_fast_cross_below_slow_exits() -> None:
    """A fresh down-cross while long returns EXIT."""
    params = MACrossoverParams(fast_period=2, slow_period=3)
    # Rising-then-falling closes so the fast SMA drops back below the slow SMA.
    closes = [20.0, 20.0, 20.0, 20.0, 5.0]
    position = PositionView(quantity=100.0, avg_price=20.0)
    signal = MACrossoverStrategy().evaluate(_bars(closes), position, params)

    assert signal.action is SignalAction.EXIT
    assert signal.reason


def test_no_crossover_holds() -> None:
    """A steady series with no cross returns HOLD."""
    params = MACrossoverParams(fast_period=2, slow_period=3)
    closes = [10.0, 10.0, 10.0, 10.0, 10.0]
    signal = MACrossoverStrategy().evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    """Fewer bars than slow_period + 1 returns HOLD rather than erroring."""
    params = MACrossoverParams(fast_period=2, slow_period=3)
    signal = MACrossoverStrategy().evaluate(_bars([10.0, 11.0]), None, params)

    assert signal.action is SignalAction.HOLD


def test_up_cross_while_already_long_holds() -> None:
    """An up-cross does not re-enter when a position is already held."""
    params = MACrossoverParams(fast_period=2, slow_period=3)
    closes = [10.0, 10.0, 10.0, 10.0, 20.0]
    position = PositionView(quantity=100.0, avg_price=10.0)
    signal = MACrossoverStrategy().evaluate(_bars(closes), position, params)

    assert signal.action is SignalAction.HOLD


def test_params_reject_fast_ge_slow() -> None:
    """fast_period must be strictly less than slow_period."""
    with pytest.raises(ValueError):
        MACrossoverParams(fast_period=50, slow_period=20)


def test_registry_resolves_required_history_and_params() -> None:
    """The registry resolves MA Crossover, its history need, and params schema."""
    registration = get_strategy("ma_crossover")

    assert registration.params_schema is MACrossoverParams
    # required_history = slow_period + 1
    assert registration.required_history({"fast_period": 10, "slow_period": 30}) == 31

    parsed = registration.parse_params({"fast_period": 10, "slow_period": 30})
    assert isinstance(parsed, MACrossoverParams)
    assert parsed.fast_period == 10


def test_registry_rejects_unknown_strategy() -> None:
    """An unregistered key raises UnknownStrategyError."""
    with pytest.raises(UnknownStrategyError):
        get_strategy("does_not_exist")


def test_registry_rejects_invalid_params() -> None:
    """Invalid params surface as the domain InvalidStrategyParamsError."""
    registration = get_strategy("ma_crossover")
    with pytest.raises(InvalidStrategyParamsError):
        registration.parse_params({"fast_period": 50, "slow_period": 20})


def test_list_strategies_includes_ma_crossover() -> None:
    """The catalog lists the single v1 strategy."""
    keys = {reg.key.value for reg in list_strategies()}
    assert "ma_crossover" in keys
