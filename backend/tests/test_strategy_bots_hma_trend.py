"""Unit tests for the HMA Trend strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.hma_trend import HmaTrendParams, HmaTrendStrategy, hma, wma
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = HmaTrendStrategy()
_PARAMS = HmaTrendParams(fast_period=4, slow_period=9)  # needs 12 bars
_LONG = PositionView(quantity=10, avg_price=100.0)


def _bars(closes: Sequence[float]) -> list[Bar]:
    return [
        Bar(timestamp=_START + timedelta(minutes=5 * i), open=c, high=c, low=c, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


def _state(closes: list[float]) -> tuple[float, float, float]:
    fast = hma(closes, 4)
    slow = hma(closes, 9)
    prev = hma(closes[:-1], 4)
    assert fast is not None and slow is not None and prev is not None
    return fast, slow, fast - prev


def _first_prefix(
    closes: list[float], predicate: Callable[[float, float, float], bool]
) -> list[float]:
    for end in range(_PARAMS.required_history, len(closes) + 1):
        if predicate(*_state(closes[:end])):
            return closes[:end]
    raise AssertionError("no prefix matches")


# --- helpers ------------------------------------------------------------------------------
def test_wma_weights_the_latest_value_most() -> None:
    assert wma([1, 2, 3], 3) == pytest.approx((1 + 4 + 9) / 6)
    assert wma([10, 1, 2, 3], 3) == pytest.approx((1 + 4 + 9) / 6)  # only the latest three


def test_hma_of_a_linear_series_is_the_latest_value() -> None:
    closes = [100 + 2 * i for i in range(20)]
    assert hma(closes, 9) == pytest.approx(closes[-1])


def test_hma_is_smoothed_unlike_the_course_raw_value() -> None:
    closes = [100 + (i % 5) * 3 + 0.2 * i * i for i in range(30)]
    raw = 2 * wma(closes, 4) - wma(closes, 9)
    smoothed = hma(closes, 9)
    assert smoothed is not None
    assert smoothed != pytest.approx(raw)
    assert hma(closes[:10], 9) is None  # needs 9 + 3 − 1 = 11 closes


# --- contract -------------------------------------------------------------------------------
def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.HMA_TREND)
    assert registration.display_name == "HMA Trend"
    assert registration.params_schema is HmaTrendParams


def test_params_defaults_and_validation() -> None:
    params = HmaTrendParams()
    assert (params.fast_period, params.slow_period, params.required_history) == (9, 21, 25)
    for bad in ({"fast_period": 21, "slow_period": 21}, {"fast_period": 1}, {"fast": 9}):
        with pytest.raises(ValidationError):
            HmaTrendParams.model_validate(bad)


# --- signals -------------------------------------------------------------------------------
# Accelerating rise that rounds over into a decline (and its mirror image): on a
# straight line both Hull averages equal the latest price, so curvature is needed to
# put the fast HMA above or below the slow one.
_PEAK = [100 + 0.05 * i * i for i in range(25)] + [130.0, 130.5, 130.6, 130.4, 130.0, 129.4, 128.6]
_TROUGH = [200 - 0.05 * i * i for i in range(25)] + [
    170.0,
    169.5,
    169.4,
    169.6,
    170.0,
    170.6,
    171.4,
]


def test_rising_fast_above_slow_enters() -> None:
    closes = _first_prefix(_PEAK, lambda f, s, slope: f > s and slope > 0)

    assert _STRATEGY.evaluate(_bars(closes), None, _PARAMS).action is SignalAction.ENTER_LONG


def test_fast_above_but_falling_holds() -> None:
    closes = _first_prefix(_TROUGH, lambda f, s, slope: f > s and slope < 0)

    assert _STRATEGY.evaluate(_bars(closes), None, _PARAMS).action is SignalAction.HOLD


def test_trend_reversal_exits() -> None:
    closes = _first_prefix(_PEAK, lambda f, s, slope: f < s and slope < 0)

    signal = _STRATEGY.evaluate(_bars(closes), _LONG, _PARAMS)

    assert signal.action is SignalAction.EXIT
    assert "reversal" in signal.reason


def test_below_but_rising_holds() -> None:
    closes = _first_prefix(_PEAK, lambda f, s, slope: f < s and slope > 0)

    assert _STRATEGY.evaluate(_bars(closes), _LONG, _PARAMS).action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars([100.0] * 11), None, _PARAMS).action is SignalAction.HOLD


def test_never_signals_a_short() -> None:
    closes = [200 - 1.5 * i for i in range(40)]
    for end in range(12, len(closes) + 1):
        action = _STRATEGY.evaluate(_bars(closes[:end]), None, _PARAMS).action
        assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
