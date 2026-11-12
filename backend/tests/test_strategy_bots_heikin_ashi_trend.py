"""Unit tests for the Heikin-Ashi Trend strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.heikin_ashi_trend import (
    HeikinAshiTrendParams,
    HeikinAshiTrendStrategy,
    heikin_ashi,
    strong_volume,
)
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = HeikinAshiTrendStrategy()
_PLAIN = HeikinAshiTrendParams()
_VOLUME = HeikinAshiTrendParams(volume_filter=True, volume_window=5)
_LONG = PositionView(quantity=10, avg_price=100.0)


def _bars(
    ohlc: Sequence[tuple[float, float, float, float]], volumes: Sequence[float] | None = None
) -> list[Bar]:
    vols = list(volumes) if volumes is not None else [1_000.0] * len(ohlc)
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        for i, ((o, h, lo, c), v) in enumerate(zip(ohlc, vols, strict=True))
    ]


def _rising(n: int) -> list[tuple[float, float, float, float]]:
    return [(100 + i, 101.5 + i, 99.5 + i, 101 + i) for i in range(n)]


def _falling(n: int) -> list[tuple[float, float, float, float]]:
    return [(200 - i, 200.5 - i, 198.5 - i, 199 - i) for i in range(n)]


# --- candles -----------------------------------------------------------------------------
def test_heikin_ashi_matches_a_hand_computed_series() -> None:
    first, second = heikin_ashi(_bars([(10, 12, 9, 11), (11, 14, 11, 13)]))

    assert (first.open, first.close, first.green) == (10.5, 10.5, False)
    assert (second.open, second.close) == (10.5, 12.25)
    assert (second.high, second.low, second.green) == (14, 10.5, True)


def test_strong_volume_compares_the_latest_bar_with_the_window_mean() -> None:
    bars = _bars(_rising(5), volumes=[100, 100, 100, 100, 200])
    assert strong_volume(bars, 5) is True  # 200 > mean 120
    assert strong_volume(_bars(_rising(5), volumes=[100] * 5), 5) is False  # equal
    assert strong_volume(_bars(_rising(5), volumes=[0] * 5), 5) is False  # no volume


# --- contract ---------------------------------------------------------------------------
def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.HEIKIN_ASHI_TREND)
    assert registration.display_name == "Heikin-Ashi Trend"
    assert registration.params_schema is HeikinAshiTrendParams


def test_params_and_required_history() -> None:
    assert (_PLAIN.volume_filter, _PLAIN.volume_window, _PLAIN.required_history) == (False, 20, 10)
    assert HeikinAshiTrendParams(volume_filter=True).required_history == 20
    assert HeikinAshiTrendParams(volume_filter=True, volume_window=5).required_history == 10
    for bad in ({"volume_window": 1}, {"volume": True}):
        with pytest.raises(ValidationError):
            HeikinAshiTrendParams.model_validate(bad)


# --- plain ------------------------------------------------------------------------------------
def test_green_candle_enters() -> None:
    assert _STRATEGY.evaluate(_bars(_rising(12)), None, _PLAIN).action is SignalAction.ENTER_LONG


def test_red_candle_stays_flat() -> None:
    assert _STRATEGY.evaluate(_bars(_falling(12)), None, _PLAIN).action is SignalAction.HOLD


def test_red_candle_exits_and_green_holds() -> None:
    assert _STRATEGY.evaluate(_bars(_falling(12)), _LONG, _PLAIN).action is SignalAction.EXIT
    assert _STRATEGY.evaluate(_bars(_rising(12)), _LONG, _PLAIN).action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars(_rising(9)), None, _PLAIN).action is SignalAction.HOLD


# --- volume filter ------------------------------------------------------------------------------
def test_green_without_strong_volume_holds() -> None:
    bars = _bars(_rising(12), volumes=[100] * 12)

    signal = _STRATEGY.evaluate(bars, None, _VOLUME)

    assert signal.action is SignalAction.HOLD
    assert "volume" in signal.reason


def test_green_with_strong_volume_enters() -> None:
    bars = _bars(_rising(12), volumes=[100] * 11 + [300])

    assert _STRATEGY.evaluate(bars, None, _VOLUME).action is SignalAction.ENTER_LONG


def test_fading_volume_exits_even_on_green() -> None:
    bars = _bars(_rising(12), volumes=[300] * 11 + [100])

    signal = _STRATEGY.evaluate(bars, _LONG, _VOLUME)

    assert signal.action is SignalAction.EXIT
    assert "volume faded" in signal.reason


def test_red_exits_with_the_filter_on() -> None:
    bars = _bars(_falling(12), volumes=[100] * 11 + [300])

    assert _STRATEGY.evaluate(bars, _LONG, _VOLUME).action is SignalAction.EXIT


def test_never_signals_a_short() -> None:
    for ohlc in (_falling(15), _rising(15)):
        for params in (_PLAIN, _VOLUME):
            action = _STRATEGY.evaluate(_bars(ohlc), None, params).action
            assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
