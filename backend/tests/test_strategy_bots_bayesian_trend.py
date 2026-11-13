"""Unit tests for the Bayesian Trend Predictor strategy (pure, no DB)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.bayesian_trend import (
    BayesianTrendParams,
    BayesianTrendStrategy,
    most_likely,
    posterior,
)
from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=100.0)
_STRATEGY = BayesianTrendStrategy()
_PARAMS = BayesianTrendParams()


def _compound(step: float, n: int = 21) -> list[float]:
    """``n`` closes moving by ``step`` (a fraction) every bar."""
    return [100.0 * (1 + step) ** i for i in range(n)]


_UP = _compound(0.002)
_DOWN = _compound(-0.002)
_FLAT = [100.0] * 21


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
    params: BayesianTrendParams = _PARAMS,
) -> SignalAction:
    return _STRATEGY.evaluate(_bars(closes), position, params).action


def _course_pdf(x: float, mu: float, sigma: float) -> float:
    return 1 / (math.sqrt(2 * math.pi) * sigma) * math.exp(-0.5 * ((x - mu) / sigma) ** 2)


def test_registered_and_satisfies_protocol() -> None:
    registration = get_strategy(StrategyKey.BAYESIAN_TREND.value)
    assert registration.display_name == "Bayesian Trend Predictor"
    assert isinstance(registration.strategy, Strategy)
    assert registration.params_schema is BayesianTrendParams


def test_defaults_match_the_course() -> None:
    assert (_PARAMS.drift, _PARAMS.trend_sigma, _PARAMS.flat_sigma) == (0.001, 0.002, 0.0008)
    assert (_PARAMS.threshold, _PARAMS.replay_bars) == (0.6, 20)
    assert _PARAMS.required_history == 21


@pytest.mark.parametrize(
    "kwargs",
    [
        {"drift": 0},
        {"trend_sigma": 0},
        {"flat_sigma": -0.001},
        {"threshold": 1 / 3},
        {"threshold": 1.0},
        {"replay_bars": 0},
        {"unknown": 1},
    ],
)
def test_invalid_params_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BayesianTrendParams(**kwargs)  # type: ignore[arg-type]


def test_rejects_foreign_params() -> None:
    from cadence.strategy_bots.vama import VamaParams

    with pytest.raises(TypeError):
        _STRATEGY.evaluate(_bars(_UP), None, VamaParams())


# Posterior -------------------------------------------------------------------
def test_single_update_matches_the_course_formula() -> None:
    params = BayesianTrendParams(replay_bars=1)
    delta = 0.002
    likelihood = {
        "UP": _course_pdf(delta, 0.001, 0.002),
        "FLAT": _course_pdf(delta, 0.0, 0.0008),
        "DOWN": _course_pdf(delta, -0.001, 0.002),
    }
    total = sum(likelihood.values())

    result = posterior([100.0, 100.2], params)

    for state, value in likelihood.items():
        assert result[state] == pytest.approx(value / total)


def test_sequential_update_uses_each_posterior_as_the_next_prior() -> None:
    closes = [100.0, 100.2, 100.1, 100.3]
    prior = {"UP": 1 / 3, "FLAT": 1 / 3, "DOWN": 1 / 3}
    for previous, current in pairwise(closes):
        delta = (current - previous) / previous
        unnorm = {
            "UP": prior["UP"] * _course_pdf(delta, 0.001, 0.002),
            "FLAT": prior["FLAT"] * _course_pdf(delta, 0.0, 0.0008),
            "DOWN": prior["DOWN"] * _course_pdf(delta, -0.001, 0.002),
        }
        total = sum(unnorm.values())
        prior = {state: value / total for state, value in unnorm.items()}

    result = posterior(closes, BayesianTrendParams(replay_bars=3))
    for state, value in prior.items():
        assert result[state] == pytest.approx(value)


def test_only_the_latest_replay_bars_count() -> None:
    # A long down-run before the window is ignored.
    closes = _compound(-0.003, 30) + _compound(0.002, 21)[1:]
    assert most_likely(posterior(closes, _PARAMS))[0] == "UP"


def test_extreme_return_keeps_its_direction() -> None:
    # +50% underflows every linear likelihood; the course would reset to uniform.
    params = BayesianTrendParams(replay_bars=1)
    assert _course_pdf(0.5, 0.001, 0.002) == 0.0
    state, probability = most_likely(posterior([100.0, 150.0], params))
    assert state == "UP" and probability > 0.99


def test_tie_resolves_up_first() -> None:
    assert most_likely({"UP": 0.4, "FLAT": 0.4, "DOWN": 0.2}) == ("UP", 0.4)


# Signals ---------------------------------------------------------------------
def test_enters_a_confident_up_regime() -> None:
    signal = _STRATEGY.evaluate(_bars(_UP), None, _PARAMS)
    assert signal.action is SignalAction.ENTER_LONG
    assert "P(up)" in signal.reason


def test_does_not_enter_a_flat_regime() -> None:
    assert most_likely(posterior(_FLAT, _PARAMS))[0] == "FLAT"
    assert _action(_FLAT) is SignalAction.HOLD


def test_does_not_enter_below_the_threshold() -> None:
    # Δ = 0.12%: UP is most likely but only ~42%.
    params = BayesianTrendParams(replay_bars=1)
    state, probability = most_likely(posterior([100.0, 100.12], params))
    assert state == "UP" and probability < 0.6
    assert _action([100.0, 100.12], params=params) is SignalAction.HOLD


def test_does_not_enter_a_down_regime() -> None:
    assert _action(_DOWN) is SignalAction.HOLD


def test_holds_through_flat_and_up() -> None:
    assert _action(_FLAT, _LONG) is SignalAction.HOLD
    assert _action(_UP, _LONG) is SignalAction.HOLD


def test_exits_a_confident_down_regime() -> None:
    assert _action(_DOWN, _LONG) is SignalAction.EXIT


def test_insufficient_history_holds() -> None:
    assert _action(_UP[1:]) is SignalAction.HOLD
    assert _action(_DOWN[1:], _LONG) is SignalAction.HOLD


def test_never_signals_short() -> None:
    for closes in (_UP, _DOWN, _FLAT):
        assert _action(closes) in {SignalAction.HOLD, SignalAction.ENTER_LONG}
