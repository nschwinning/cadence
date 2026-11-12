"""Unit tests for the ATR-Band Trend strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.atr_band_trend import (
    AtrBandTrendParams,
    AtrBandTrendStrategy,
    mean_abs_close_change,
    supertrend,
)
from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=100.0)
_STRATEGY = AtrBandTrendStrategy()
_SUPER = AtrBandTrendParams(version="supertrend", window=5, atr_mult=1.0)
_KELTNER = AtrBandTrendParams(version="keltner", window=5, atr_mult=1.0)


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


def _zigzag_up(n: int) -> list[float]:
    """A rising series with alternating steps (non-zero ATR)."""
    return [100.0 + i * 1.0 + (0.5 if i % 2 else 0.0) for i in range(n)]


def _zigzag_down(n: int) -> list[float]:
    return [200.0 - i * 1.0 - (0.5 if i % 2 else 0.0) for i in range(n)]


# --- contract ------------------------------------------------------------------------------
def test_satisfies_the_strategy_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.ATR_BAND_TREND)
    assert registration.display_name == "ATR-Band Trend"
    assert registration.params_schema is AtrBandTrendParams


def test_params_defaults_and_validation() -> None:
    params = AtrBandTrendParams()
    assert (params.version, params.window, params.atr_mult, params.exit_on_midline) == (
        "supertrend",
        20,
        3.0,
        True,
    )
    assert params.required_history == 60
    assert AtrBandTrendParams(version="keltner").required_history == 20
    with pytest.raises(ValidationError):
        AtrBandTrendParams(window=1)
    with pytest.raises(ValidationError):
        AtrBandTrendParams(atr_mult=0)
    with pytest.raises(ValidationError):
        AtrBandTrendParams(version="donchian")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AtrBandTrendParams.model_validate({"windw": 5})


def test_atr_is_the_mean_absolute_close_change() -> None:
    assert mean_abs_close_change([10, 12, 11, 15]) == pytest.approx((2 + 1 + 4) / 3)
    assert mean_abs_close_change([10]) == 0.0


def test_insufficient_history_holds() -> None:
    signal = _STRATEGY.evaluate(_bars(_zigzag_up(14)), None, _SUPER)  # needs 15
    assert signal.action is SignalAction.HOLD


# --- SuperTrend ----------------------------------------------------------------------------
def test_supertrend_enters_in_an_up_trend_above_the_line() -> None:
    closes = _zigzag_up(30)
    state = supertrend(closes, 5, 1.0)
    assert state is not None and state.trend == "up" and closes[-1] > state.line

    signal = _STRATEGY.evaluate(_bars(closes), None, _SUPER)

    assert signal.action is SignalAction.ENTER_LONG


def test_supertrend_does_not_enter_in_a_down_trend() -> None:
    closes = _zigzag_down(30)
    state = supertrend(closes, 5, 1.0)
    assert state is not None and state.trend == "down"

    assert _STRATEGY.evaluate(_bars(closes), None, _SUPER).action is SignalAction.HOLD


def test_supertrend_holds_in_a_position_even_after_a_down_turn() -> None:
    closes = _zigzag_up(20) + _zigzag_down(10)

    signal = _STRATEGY.evaluate(_bars(closes), _LONG, _SUPER)

    assert signal.action is SignalAction.HOLD
    assert "engine" in signal.reason


def test_supertrend_lower_band_never_falls_in_an_up_trend() -> None:
    closes = _zigzag_up(40)
    lowers = []
    for end in range(10, len(closes) + 1):
        state = supertrend(closes[:end], 5, 1.0)
        assert state is not None
        lowers.append((state.trend, state.lower))
    up_lowers = [lower for trend, lower in lowers if trend == "up"]
    assert up_lowers == sorted(up_lowers)


def test_supertrend_replay_is_deterministic() -> None:
    bars = _bars(_zigzag_up(20) + _zigzag_down(5) + _zigzag_up(10))
    first = _STRATEGY.evaluate(bars, None, _SUPER)
    second = _STRATEGY.evaluate(bars, None, _SUPER)
    assert first == second


# --- Keltner -----------------------------------------------------------------------------------
def test_keltner_enters_above_the_upper_band() -> None:
    closes = [100, 101, 100, 101, 110]  # mean 102.4, ATR 3.25 → upper 105.65

    signal = _STRATEGY.evaluate(_bars(closes), None, _KELTNER)

    assert signal.action is SignalAction.ENTER_LONG


def test_keltner_stays_flat_inside_the_band() -> None:
    closes = [100, 102, 100, 102, 101]  # mean 101, ATR 1.75 → upper 102.75

    assert _STRATEGY.evaluate(_bars(closes), None, _KELTNER).action is SignalAction.HOLD


def test_keltner_exits_below_the_midline() -> None:
    closes = [104, 105, 104, 105, 100]  # mean 103.6 > close 100

    signal = _STRATEGY.evaluate(_bars(closes), _LONG, _KELTNER)

    assert signal.action is SignalAction.EXIT


def test_keltner_without_midline_exit_holds() -> None:
    params = AtrBandTrendParams(version="keltner", window=5, atr_mult=1.0, exit_on_midline=False)
    closes = [104, 105, 104, 105, 100]

    assert _STRATEGY.evaluate(_bars(closes), _LONG, params).action is SignalAction.HOLD


def test_never_signals_a_short() -> None:
    for closes in (_zigzag_down(30), [100, 101, 100, 101, 80] * 6):
        for params in (_SUPER, _KELTNER):
            signal = _STRATEGY.evaluate(_bars(closes), None, params)
            assert signal.action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
