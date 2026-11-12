"""Unit tests for the VAMA strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy
from cadence.strategy_bots.vama import VamaParams, VamaStrategy, smoothing_factors, vama

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_STRATEGY = VamaStrategy()
_FIXED = VamaParams(lookback=3)  # needs 12 bars
_LONG = PositionView(quantity=10, avg_price=100.0)


def _bars(closes: Sequence[float]) -> list[Bar]:
    return [
        Bar(timestamp=_START + timedelta(minutes=5 * i), open=c, high=c, low=c, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


# --- smoothing --------------------------------------------------------------------------
def test_fixed_smoothing_is_alpha_max_on_moving_prices() -> None:
    alphas = smoothing_factors([10, 11, 12, 11, 13], VamaParams(lookback=3))
    assert alphas == [None, None, 0.2, 0.2, 0.2]


def test_fixed_smoothing_is_alpha_min_on_flat_prices() -> None:
    assert smoothing_factors([10, 10, 10], VamaParams(lookback=3))[-1] == 0.02


def test_adaptive_smoothing_scales_with_relative_volatility() -> None:
    params = VamaParams(lookback=2, adaptive=True)
    # vols: [None, 3, 1] → average 2 → α = 0.2 × 1 / 2 = 0.1
    assert smoothing_factors([0, 6, 8], params)[-1] == pytest.approx(0.1)
    # vols: [None, 3, 0.1] → raw 0.2 × 0.1 / 1.55 ≈ 0.013 → clamped to α_min
    assert smoothing_factors([0, 6, 6.2], params)[-1] == pytest.approx(0.02)
    # α is not defined before 2 × lookback − 1 bars
    assert smoothing_factors([0, 6], params) == [None, None]


def test_replay_matches_a_hand_computed_series() -> None:
    params = VamaParams(lookback=2, alpha_min=0.1, alpha_max=0.5)
    # starts at 12 (first bar with α), then 0.5 × 14 + 0.5 × 12 = 13
    assert vama([10, 12, 14], params) == pytest.approx(13.0)


# --- contract ---------------------------------------------------------------------------------
def test_satisfies_the_protocol_and_is_registered() -> None:
    assert isinstance(_STRATEGY, Strategy)
    registration = get_strategy(StrategyKey.VAMA)
    assert registration.display_name == "VAMA"
    assert registration.params_schema is VamaParams


def test_params_defaults_and_validation() -> None:
    params = VamaParams()
    assert (params.lookback, params.alpha_min, params.alpha_max, params.adaptive) == (
        20,
        0.02,
        0.2,
        False,
    )
    assert params.required_history == 80
    assert VamaParams(adaptive=True).required_history == 100
    for bad in (
        {"alpha_min": 0.2, "alpha_max": 0.2},
        {"alpha_max": 1.5},
        {"lookback": 1},
        {"look": 2},
    ):
        with pytest.raises(ValidationError):
            VamaParams.model_validate(bad)


# --- signals ----------------------------------------------------------------------------------
def test_close_above_the_vama_enters() -> None:
    closes = [100 + (i % 2) for i in range(12)] + [105]
    assert _STRATEGY.evaluate(_bars(closes), None, _FIXED).action is SignalAction.ENTER_LONG


def test_close_below_the_vama_stays_flat() -> None:
    closes = [100 + (i % 2) for i in range(12)] + [95]
    assert _STRATEGY.evaluate(_bars(closes), None, _FIXED).action is SignalAction.HOLD


def test_close_at_or_below_the_vama_exits() -> None:
    closes = [100 + (i % 2) for i in range(12)] + [95]

    signal = _STRATEGY.evaluate(_bars(closes), _LONG, _FIXED)

    assert signal.action is SignalAction.EXIT
    assert "fixed VAMA" in signal.reason


def test_holding_above_the_vama_holds() -> None:
    closes = [100 + (i % 2) for i in range(12)] + [105]
    assert _STRATEGY.evaluate(_bars(closes), _LONG, _FIXED).action is SignalAction.HOLD


def test_adaptive_mode_trades_too() -> None:
    params = VamaParams(lookback=3, adaptive=True)  # needs 15 bars
    closes = [100 + (i % 2) for i in range(15)] + [105]

    signal = _STRATEGY.evaluate(_bars(closes), None, params)

    assert signal.action is SignalAction.ENTER_LONG
    assert "adaptive VAMA" in signal.reason


def test_insufficient_history_holds() -> None:
    assert _STRATEGY.evaluate(_bars([100.0] * 11), None, _FIXED).action is SignalAction.HOLD


def test_never_signals_a_short() -> None:
    closes = [200 - i for i in range(30)]
    for end in range(12, len(closes) + 1):
        action = _STRATEGY.evaluate(_bars(closes[:end]), None, _FIXED).action
        assert action in (SignalAction.HOLD, SignalAction.ENTER_LONG)
