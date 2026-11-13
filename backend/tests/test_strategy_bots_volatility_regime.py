"""Unit tests for the Volatility Regime Switcher strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy
from cadence.strategy_bots.volatility_regime import (
    VolatilityRegimeParams,
    VolatilityRegimeStrategy,
    regime,
    rolling_atr,
)

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=100.0)
_STRATEGY = VolatilityRegimeStrategy()
# ATR over 3 closes, SMA over 4, baseline over the latest 4 ATRs → 6 bars needed.
_PARAMS = VolatilityRegimeParams(atr_window=3, sma_period=4, baseline_bars=4)

# Volatile start, calm finish: ATRs 4, 4, 2.25, 0.5 → baseline 2.6875, trend.
_CALM_UP = [100.0, 104.0, 100.0, 104.0, 104.5, 105.0]  # HL2 104.5, close above
_CALM_DOWN = [100.0, 104.0, 100.0, 104.0, 104.5, 104.1]  # HL2 104.25, close below
_CALM_AT = [100.0, 104.0, 100.0, 104.0, 104.5, 104.25]  # close on HL2
# Calm start, volatile finish: reversion.
_WILD_DIP = [100.0, 100.1, 100.0, 100.1, 104.0, 99.0]  # SMA 100.775, close below
_WILD_UP = [100.0, 100.1, 100.0, 100.1, 96.0, 101.0]  # SMA 99.275, close above


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


def _action(
    closes: Sequence[float],
    position: PositionView | None = None,
    params: VolatilityRegimeParams = _PARAMS,
) -> SignalAction:
    return _STRATEGY.evaluate(_bars(closes), position, params).action


def test_registered_and_satisfies_protocol() -> None:
    registration = get_strategy(StrategyKey.VOLATILITY_REGIME.value)
    assert registration.display_name == "Volatility Regime Switcher"
    assert isinstance(registration.strategy, Strategy)
    assert registration.params_schema is VolatilityRegimeParams


def test_defaults_match_the_course_and_history() -> None:
    params = VolatilityRegimeParams()
    assert (params.atr_window, params.sma_period, params.baseline_bars) == (20, 20, 100)
    assert params.reversion_deviation == 0.0
    assert params.required_history == 119
    assert (
        VolatilityRegimeParams(atr_window=2, sma_period=50, baseline_bars=10).required_history == 50
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"atr_window": 1},
        {"sma_period": 1},
        {"baseline_bars": 1},
        {"reversion_deviation": -0.01},
        {"reversion_deviation": 1.0},
        {"unknown": 1},
    ],
)
def test_invalid_params_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VolatilityRegimeParams(**kwargs)  # type: ignore[arg-type]


def test_rejects_foreign_params() -> None:
    from cadence.strategy_bots.vama import VamaParams

    with pytest.raises(TypeError):
        _STRATEGY.evaluate(_bars([1.0] * 200), None, VamaParams())


def test_rolling_atr_and_regime() -> None:
    assert rolling_atr(_CALM_UP, 3, 4) == pytest.approx([4.0, 4.0, 2.25, 0.5])
    mode, atr, baseline = regime(_CALM_UP, _PARAMS)
    assert (mode, atr, baseline) == ("trend", pytest.approx(0.5), pytest.approx(2.6875))
    assert regime(_WILD_DIP, _PARAMS)[0] == "reversion"


def test_atr_equal_to_baseline_is_trend() -> None:
    flat = [100.0] * 6
    assert regime(flat, _PARAMS) == ("trend", 0.0, 0.0)
    assert _action(flat) is SignalAction.HOLD  # close on HL2


def test_insufficient_history_holds() -> None:
    assert _action(_CALM_UP[1:]) is SignalAction.HOLD
    assert _action(_WILD_UP[1:], _LONG) is SignalAction.HOLD


# Trend regime ----------------------------------------------------------------
def test_calm_market_enters_above_hl2() -> None:
    assert _action(_CALM_UP) is SignalAction.ENTER_LONG


def test_calm_market_holds_position_above_hl2() -> None:
    assert _action(_CALM_UP, _LONG) is SignalAction.HOLD


def test_calm_market_exits_below_hl2() -> None:
    assert _action(_CALM_DOWN, _LONG) is SignalAction.EXIT
    assert _action(_CALM_DOWN) is SignalAction.HOLD


def test_close_on_hl2_neither_enters_nor_exits() -> None:
    assert _action(_CALM_AT) is SignalAction.HOLD
    assert _action(_CALM_AT, _LONG) is SignalAction.HOLD


# Reversion regime ------------------------------------------------------------
def test_volatile_market_enters_below_the_sma() -> None:
    assert _action(_WILD_DIP) is SignalAction.ENTER_LONG


def test_deviation_blocks_a_shallow_dip() -> None:
    deep = VolatilityRegimeParams(
        atr_window=3, sma_period=4, baseline_bars=4, reversion_deviation=0.05
    )
    assert _action(_WILD_DIP, params=deep) is SignalAction.HOLD


def test_volatile_market_holds_below_the_sma() -> None:
    assert _action(_WILD_DIP, _LONG) is SignalAction.HOLD


def test_volatile_market_does_not_buy_strength() -> None:
    assert _action(_WILD_UP) is SignalAction.HOLD


def test_volatile_market_exits_on_the_revert() -> None:
    assert _action(_WILD_UP, _LONG) is SignalAction.EXIT


def test_never_signals_short() -> None:
    for closes in (_CALM_UP, _CALM_DOWN, _WILD_DIP, _WILD_UP):
        assert _action(closes) in {SignalAction.HOLD, SignalAction.ENTER_LONG}
