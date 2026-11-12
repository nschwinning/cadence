"""Unit tests for the Trend Confirmation strategy (pure, no DB).

Real-maths tests use synthetic price paths; the leg-logic tests pin the indicator values
with a fake series module so each leg can be set precisely (e.g. an RSI of exactly 47).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from cadence.strategy_bots import trend_confirmation as tc
from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy
from cadence.strategy_bots.trend_confirmation import (
    TrendConfirmationParams,
    TrendConfirmationStrategy,
)
from cadence.technical_indicators import series as real_series

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = TrendConfirmationStrategy()
_PARAMS = TrendConfirmationParams()  # needs 87 bars
_LONG = PositionView(quantity=10, avg_price=100.0)


def _bars(closes: Sequence[float], volume: float = 1_000.0) -> list[Bar]:
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=volume,
        )
        for i, c in enumerate(closes)
    ]


_RISING = [100 + 0.15 * i + (1.5 if i % 2 else 0) + 0.001 * i * i for i in range(90)]
_FALLING = [200 - 0.1 * i - (0.6 if i % 2 else 0) for i in range(90)]
_FLAT_BARS = _bars([100.0] * 90)


def _fake_series(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sma_fast: float = 105.0,
    sma_slow: float = 100.0,
    hist: float = 0.2,
    rsi: float = 60.0,
    roc: float = 0.01,
    obv_change: float = 1_000.0,
) -> None:
    """Make the strategy see fixed latest indicator values."""

    def const(value: float) -> pd.Series:
        return pd.Series([value])

    def sma(_price: pd.Series, n: int) -> pd.Series:
        return const(sma_fast if n == 20 else sma_slow)

    fake = SimpleNamespace(
        sma=sma,
        macd=lambda *_a: SimpleNamespace(histogram=const(hist)),
        rsi=lambda *_a: const(rsi),
        roc=lambda *_a: const(roc),
        obv=lambda *_a: const(0.0),
        change=lambda *_a: const(obv_change),
    )
    monkeypatch.setattr(tc, "series", fake)


# --- contract ---------------------------------------------------------------------------------
def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.TREND_CONFIRMATION)
    assert registration.display_name == "Trend Confirmation"
    assert registration.params_schema is TrendConfirmationParams


def test_params_defaults_and_validation() -> None:
    assert _PARAMS.required_history == 87
    assert (_PARAMS.rsi_exit, _PARAMS.rsi_entry, _PARAMS.rsi_max) == (45, 50, 70)
    for bad in (
        {"sma_fast": 50, "sma_slow": 50},
        {"macd_fast": 26, "macd_slow": 26},
        {"rsi_exit": 55},  # above the entry level
        {"rsi_entry": 70},  # not below the cap
        {"sma": 20},
    ):
        with pytest.raises(ValidationError):
            TrendConfirmationParams.model_validate(bad)


# --- real maths ------------------------------------------------------------------------------------
def test_rising_trend_with_moderate_rsi_enters() -> None:
    signal = _STRATEGY.evaluate(_bars(_RISING), None, _PARAMS)

    assert signal.action is SignalAction.ENTER_LONG
    assert "all trend legs agree" in signal.reason


def test_falling_trend_holds_flat_and_exits_a_position() -> None:
    assert _STRATEGY.evaluate(_bars(_FALLING), None, _PARAMS).action is SignalAction.HOLD
    assert _STRATEGY.evaluate(_bars(_FALLING), _LONG, _PARAMS).action is SignalAction.EXIT


def test_flat_prices_leave_rsi_undefined_and_hold() -> None:
    signal = _STRATEGY.evaluate(_FLAT_BARS, None, _PARAMS)

    assert signal.action is SignalAction.HOLD
    assert "rsi" in signal.reason


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars(_RISING[:86]), None, _PARAMS).action is SignalAction.HOLD


def test_uses_the_shared_gate_maths() -> None:
    assert tc.series is real_series


# --- leg logic (fixed indicator values) ------------------------------------------------------------
def test_rsi_at_or_above_the_cap_blocks_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, rsi=70.0)

    signal = _STRATEGY.evaluate(_FLAT_BARS, None, _PARAMS)

    assert signal.action is SignalAction.HOLD
    assert "outside" in signal.reason


def test_negative_macd_histogram_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, hist=-0.01)

    signal = _STRATEGY.evaluate(_FLAT_BARS, _LONG, _PARAMS)

    assert signal.action is SignalAction.EXIT
    assert "MACD histogram negative" in signal.reason


def test_rsi_hysteresis_holds_between_exit_and_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, rsi=47.0)

    assert _STRATEGY.evaluate(_FLAT_BARS, _LONG, _PARAMS).action is SignalAction.HOLD
    assert _STRATEGY.evaluate(_FLAT_BARS, None, _PARAMS).action is SignalAction.HOLD


def test_rsi_below_the_exit_level_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, rsi=44.0)

    assert _STRATEGY.evaluate(_FLAT_BARS, _LONG, _PARAMS).action is SignalAction.EXIT


def test_strength_above_the_cap_is_not_sold(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, rsi=85.0)

    assert _STRATEGY.evaluate(_FLAT_BARS, _LONG, _PARAMS).action is SignalAction.HOLD


def test_broken_trend_regime_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch, sma_fast=99.0, sma_slow=100.0)

    assert _STRATEGY.evaluate(_FLAT_BARS, _LONG, _PARAMS).action is SignalAction.EXIT


@pytest.mark.parametrize(
    ("flag", "override"),
    [("use_roc", {"roc": -0.01}), ("use_obv", {"obv_change": -500.0})],
)
def test_optional_legs_join_the_conjunction(
    monkeypatch: pytest.MonkeyPatch, flag: str, override: dict[str, float]
) -> None:
    _fake_series(monkeypatch, **override)
    params = TrendConfirmationParams.model_validate({flag: True})

    assert _STRATEGY.evaluate(_FLAT_BARS, None, params).action is SignalAction.HOLD
    assert _STRATEGY.evaluate(_FLAT_BARS, _LONG, params).action is SignalAction.EXIT
    # Disabled, the same values do not matter.
    assert _STRATEGY.evaluate(_FLAT_BARS, None, _PARAMS).action is SignalAction.ENTER_LONG


def test_all_legs_agree_with_optional_legs_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_series(monkeypatch)
    params = TrendConfirmationParams(use_roc=True, use_obv=True)

    assert _STRATEGY.evaluate(_FLAT_BARS, None, params).action is SignalAction.ENTER_LONG
