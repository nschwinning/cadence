"""Unit tests for the ADX Trend Strength strategy and the reversion ADX danger exit."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.adx_trend import (
    AdxTrendParams,
    AdxTrendStrategy,
    adx,
    directional_movement,
    window_directional_index,
)
from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.rolling_average_reversion import (
    RollingAverageReversionParams,
    RollingAverageReversionStrategy,
)
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = AdxTrendStrategy()
_PARAMS = AdxTrendParams(period=5, threshold=20)


def _bars(hlc: Sequence[tuple[float, float, float]]) -> list[Bar]:
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=1_000.0,
        )
        for i, (h, lo, c) in enumerate(hlc)
    ]


def _up(n: int, start: float = 100.0) -> list[tuple[float, float, float]]:
    """Each bar 2 higher: +DM 2, −DM 0 → a strong up-trend."""
    return [(start + 2 + 2 * i, start + 2 * i, start + 1.5 + 2 * i) for i in range(n)]


def _down(n: int, start: float = 200.0) -> list[tuple[float, float, float]]:
    return [(start + 2 - 2 * i, start - 2 * i, start + 0.5 - 2 * i) for i in range(n)]


def _chop(n: int) -> list[tuple[float, float, float]]:
    """Alternating up / down bars of equal size → +DM and −DM balance, weak trend."""
    return [(102.0, 100.0, 101.0) if i % 2 == 0 else (101.0, 99.0, 100.0) for i in range(n)]


# --- helpers ---------------------------------------------------------------------------
def test_directional_movement_matches_a_hand_computed_series() -> None:
    dm = directional_movement(_bars([(10, 8, 9), (12, 9, 11), (11, 7, 8)]))

    assert dm.tr == [3, 4]
    assert dm.plus_dm == [2, 0]
    assert dm.minus_dm == [0, 2]
    reading = window_directional_index(_bars([(10, 8, 9), (12, 9, 11), (11, 7, 8)]))
    assert reading.plus_di == pytest.approx(100 * 2 / 7)
    assert reading.minus_di == pytest.approx(100 * 2 / 7)
    assert reading.dx == pytest.approx(0.0)


def test_adx_of_a_clean_up_trend_is_maximal() -> None:
    reading = adx(_bars(_up(10)), 5)

    assert reading is not None
    assert reading.adx == pytest.approx(100.0)
    assert reading.plus_di > 0 and reading.minus_di == 0


def test_adx_needs_two_periods_of_bars() -> None:
    assert adx(_bars(_up(9)), 5) is None
    assert adx(_bars(_up(10)), 5) is not None


# --- strategy ------------------------------------------------------------------------------
def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.ADX_TREND)
    assert registration.display_name == "ADX Trend Strength"
    assert registration.params_schema is AdxTrendParams


def test_params_defaults_and_validation() -> None:
    params = AdxTrendParams()
    assert (params.period, params.threshold, params.required_history) == (10, 20.0, 20)
    for bad in ({"period": 1}, {"threshold": 0}, {"threshold": 100}, {"perod": 5}):
        with pytest.raises(ValidationError):
            AdxTrendParams.model_validate(bad)


def test_enters_a_strong_up_trend() -> None:
    assert _STRATEGY.evaluate(_bars(_up(10)), None, _PARAMS).action is SignalAction.ENTER_LONG


def test_does_not_enter_a_strong_down_trend() -> None:
    assert _STRATEGY.evaluate(_bars(_down(10)), None, _PARAMS).action is SignalAction.HOLD


# An even period makes the alternating up/down moves cancel exactly (DX 0).
_CHOP_PARAMS = AdxTrendParams(period=4, threshold=20)


def test_does_not_enter_a_weak_trend() -> None:
    assert _STRATEGY.evaluate(_bars(_chop(10)), None, _CHOP_PARAMS).action is SignalAction.HOLD


def test_exits_when_the_trend_weakens() -> None:
    position = PositionView(quantity=10, avg_price=100.0)

    assert _STRATEGY.evaluate(_bars(_chop(10)), position, _CHOP_PARAMS).action is (
        SignalAction.EXIT
    )


def test_holds_while_the_trend_stays_strong() -> None:
    position = PositionView(quantity=10, avg_price=100.0)

    assert _STRATEGY.evaluate(_bars(_up(10)), position, _PARAMS).action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars(_up(9)), None, _PARAMS).action is SignalAction.HOLD


# --- reversion ADX danger exit -----------------------------------------------------------------
_REVERSION = RollingAverageReversionStrategy()


def _reversion(adx_exit: bool) -> RollingAverageReversionParams:
    return RollingAverageReversionParams(
        average_type="typical",
        window=5,
        distance="band",
        entry_threshold=0.0,
        exit_mode="bracket",
        adx_exit=adx_exit,
        adx_lookback=5,
        adx_threshold=20.0,
    )


def test_adx_exit_closes_a_losing_trade_in_a_strong_downtrend() -> None:
    losing = PositionView(quantity=10, avg_price=250.0)

    signal = _REVERSION.evaluate(_bars(_down(10)), losing, _reversion(True))

    assert signal.action is SignalAction.EXIT
    assert "ADX danger exit" in signal.reason


def test_adx_exit_does_not_fire_in_profit() -> None:
    winning = PositionView(quantity=10, avg_price=100.0)

    assert _REVERSION.evaluate(_bars(_down(10)), winning, _reversion(True)).action is (
        SignalAction.HOLD
    )


def test_adx_exit_needs_minus_di_to_lead() -> None:
    losing = PositionView(quantity=10, avg_price=1_000.0)

    assert _REVERSION.evaluate(_bars(_up(10)), losing, _reversion(True)).action is (
        SignalAction.HOLD
    )


def test_adx_exit_needs_a_strong_trend() -> None:
    losing = PositionView(quantity=10, avg_price=1_000.0)

    assert _REVERSION.evaluate(_bars(_chop(10)), losing, _reversion(True)).action is (
        SignalAction.HOLD
    )


def test_filter_off_leaves_signals_unchanged() -> None:
    losing = PositionView(quantity=10, avg_price=250.0)
    params_off = _reversion(False)
    defaults = RollingAverageReversionParams(
        average_type="typical", window=5, distance="band", entry_threshold=0.0, exit_mode="bracket"
    )

    for bars in (_down(10), _up(10), _chop(10)):
        for position in (None, losing):
            assert _REVERSION.evaluate(_bars(bars), position, params_off) == _REVERSION.evaluate(
                _bars(bars), position, defaults
            )


def test_adx_exit_extends_the_required_history() -> None:
    params = RollingAverageReversionParams(
        window=5, adx_exit=True, adx_lookback=30, exit_mode="bracket"
    )
    assert params.required_history == 30
