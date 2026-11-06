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
from cadence.strategy_bots.rsi_mean_reversion import (
    RsiMeanReversionParams,
    RsiMeanReversionStrategy,
    _wilder_rsi,
)
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
    """The catalog lists the MA Crossover strategy."""
    keys = {reg.key.value for reg in list_strategies()}
    assert "ma_crossover" in keys


# --- RSI Mean Reversion -----------------------------------------------------


def test_rsi_strategy_satisfies_protocol() -> None:
    """The RSI strategy is recognised as a ``Strategy`` at runtime."""
    assert isinstance(RsiMeanReversionStrategy(), Strategy)


def test_wilder_rsi_all_gains_is_100() -> None:
    """A strictly rising series has zero average loss, so RSI pins to 100."""
    assert _wilder_rsi([1.0, 2.0, 3.0, 4.0], 2) == 100.0


def test_wilder_rsi_all_losses_is_0() -> None:
    """A strictly falling series has zero average gain, so RSI is 0."""
    assert _wilder_rsi([4.0, 3.0, 2.0, 1.0], 2) == 0.0


def test_wilder_rsi_known_value() -> None:
    """Wilder smoothing over a hand-computed series yields the expected RSI.

    closes [10, 11, 10, 11], period 2 → deltas +1,-1,+1; seed avg_gain=avg_loss=0.5,
    then smooth the final +1 delta: avg_gain=0.75, avg_loss=0.25, RS=3 → RSI=75.
    """
    assert _wilder_rsi([10.0, 11.0, 10.0, 11.0], 2) == pytest.approx(75.0)


def test_rsi_enter_long_when_flat_and_oversold() -> None:
    """A strictly falling series (RSI 0 < oversold) while flat returns ENTER_LONG."""
    params = RsiMeanReversionParams(period=2, oversold=30.0, exit_level=50.0)
    closes = [20.0, 18.0, 16.0, 14.0]
    signal = RsiMeanReversionStrategy().evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.ENTER_LONG
    assert signal.reason


def test_rsi_exit_when_positioned_and_reverted() -> None:
    """A strictly rising series (RSI 100 > exit_level) while long returns EXIT."""
    params = RsiMeanReversionParams(period=2, oversold=30.0, exit_level=50.0)
    closes = [14.0, 16.0, 18.0, 20.0]
    position = PositionView(quantity=100.0, avg_price=14.0)
    signal = RsiMeanReversionStrategy().evaluate(_bars(closes), position, params)

    assert signal.action is SignalAction.EXIT
    assert signal.reason


def test_rsi_oversold_while_already_long_holds() -> None:
    """An oversold reading does not re-enter when a position is already held."""
    params = RsiMeanReversionParams(period=2, oversold=30.0, exit_level=50.0)
    closes = [20.0, 18.0, 16.0, 14.0]
    position = PositionView(quantity=100.0, avg_price=20.0)
    signal = RsiMeanReversionStrategy().evaluate(_bars(closes), position, params)

    assert signal.action is SignalAction.HOLD


def test_rsi_overbought_while_flat_does_not_short() -> None:
    """An overbought reading while flat holds — the strategy is long-only."""
    params = RsiMeanReversionParams(period=2, oversold=30.0, exit_level=50.0)
    closes = [14.0, 16.0, 18.0, 20.0]
    signal = RsiMeanReversionStrategy().evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.HOLD


def test_rsi_within_band_holds() -> None:
    """An RSI reading between the oversold and exit levels returns HOLD."""
    params = RsiMeanReversionParams(period=2, oversold=30.0, exit_level=50.0)
    # Alternating closes keep RSI near the middle of the band.
    closes = [10.0, 11.0, 10.0, 11.0]
    signal = RsiMeanReversionStrategy().evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.HOLD


def test_rsi_insufficient_history_holds() -> None:
    """Fewer bars than period + 1 returns HOLD rather than erroring."""
    params = RsiMeanReversionParams(period=14)
    signal = RsiMeanReversionStrategy().evaluate(_bars([10.0, 11.0]), None, params)

    assert signal.action is SignalAction.HOLD


def test_rsi_params_defaults() -> None:
    """The params default to the course values (14 / 30 / 50)."""
    params = RsiMeanReversionParams()

    assert params.period == 14
    assert params.oversold == 30.0
    assert params.exit_level == 50.0
    assert params.required_history == 15


def test_rsi_params_reject_oversold_ge_exit() -> None:
    """oversold must be strictly below exit_level."""
    with pytest.raises(ValueError):
        RsiMeanReversionParams(oversold=60.0, exit_level=50.0)


def test_rsi_params_reject_out_of_range_threshold() -> None:
    """Thresholds outside 0–100 are rejected."""
    with pytest.raises(ValueError):
        RsiMeanReversionParams(oversold=-1.0)
    with pytest.raises(ValueError):
        RsiMeanReversionParams(exit_level=150.0)


def test_rsi_params_reject_unknown_field() -> None:
    """Extra params are forbidden (``extra='forbid'`` on the base schema)."""
    with pytest.raises(ValueError):
        RsiMeanReversionParams(unknown_field=1)  # type: ignore[call-arg]


def test_rsi_evaluate_rejects_wrong_params_type() -> None:
    """Handing the RSI strategy MA Crossover params raises TypeError."""
    with pytest.raises(TypeError):
        RsiMeanReversionStrategy().evaluate(
            _bars([10.0, 11.0, 12.0]),
            None,
            MACrossoverParams(fast_period=2, slow_period=3),
        )


def test_registry_resolves_rsi_mean_reversion() -> None:
    """The registry resolves the RSI strategy, its history need, and params."""
    registration = get_strategy("rsi_mean_reversion")

    assert registration.params_schema is RsiMeanReversionParams
    assert registration.display_name == "RSI Mean Reversion"
    assert registration.explanation
    # required_history = period + 1
    assert registration.required_history({"period": 14}) == 15

    parsed = registration.parse_params(
        {"period": 10, "oversold": 25.0, "exit_level": 55.0}
    )
    assert isinstance(parsed, RsiMeanReversionParams)
    assert parsed.period == 10


def test_registry_rsi_rejects_invalid_params() -> None:
    """Invalid RSI params surface as the domain InvalidStrategyParamsError."""
    registration = get_strategy("rsi_mean_reversion")
    with pytest.raises(InvalidStrategyParamsError):
        registration.parse_params({"oversold": 60.0, "exit_level": 50.0})


def test_list_strategies_includes_rsi_mean_reversion() -> None:
    """The catalog lists the RSI Mean Reversion strategy."""
    keys = {reg.key.value for reg in list_strategies()}
    assert "rsi_mean_reversion" in keys
