"""Unit tests for the Multi-Signal Consensus strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.signal_consensus import (
    SignalConsensusParams,
    SignalConsensusStrategy,
    simple_rsi,
    votes,
)
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=100.0)
_STRATEGY = SignalConsensusStrategy()
_PARAMS = SignalConsensusParams()

# A choppy window ending in a sharp drop: every signal votes oversold (score 8).
_DIP = [100.0] * 5 + [100, 100.5, 100, 100.5, 100, 100.5, 100, 100.5, 100, 97]
# A steady climb with a pull-back: median and gradient oversold, RSI overbought.
_PULLBACK = [100 + 0.5 * i for i in range(14)] + [104.0]
_SHALLOW = [100 + 0.5 * i for i in range(14)] + [103.5]
_FLAT = [100.0] * 15


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


def _signal(
    closes: Sequence[float],
    position: PositionView | None = None,
    params: SignalConsensusParams = _PARAMS,
):
    return _STRATEGY.evaluate(_bars(closes), position, params)


def test_registered_and_satisfies_protocol() -> None:
    registration = get_strategy(StrategyKey.SIGNAL_CONSENSUS.value)
    assert registration.display_name == "Multi-Signal Consensus"
    assert isinstance(registration.strategy, Strategy)
    assert registration.params_schema is SignalConsensusParams


def test_defaults_match_the_course() -> None:
    assert (_PARAMS.window, _PARAMS.consensus, _PARAMS.rsi_period, _PARAMS.bb_k) == (10, 3, 14, 2.0)
    assert _PARAMS.required_history == 15
    assert SignalConsensusParams(window=20).required_history == 20


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window": 4},
        {"consensus": 0},
        {"consensus": 9},
        {"rsi_period": 1},
        {"bb_k": 0},
        {"unknown": 1},
    ],
)
def test_invalid_params_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SignalConsensusParams(**kwargs)  # type: ignore[arg-type]


def test_rejects_foreign_params() -> None:
    from cadence.strategy_bots.vama import VamaParams

    with pytest.raises(TypeError):
        _STRATEGY.evaluate(_bars(_DIP), None, VamaParams())


# Votes -----------------------------------------------------------------------
def test_simple_rsi() -> None:
    assert simple_rsi([1.0, 2.0, 3.0]) == 100.0  # no losses
    assert simple_rsi([3.0, 2.0, 1.0]) == 0.0  # no gains
    assert simple_rsi([1.0, 2.0, 1.0]) == pytest.approx(50.0)


def test_sharp_drop_draws_every_oversold_vote() -> None:
    assert votes(_DIP, _PARAMS) == dict.fromkeys(
        ["Z", "SMA", "RSI", "BB", "PCTL", "MED", "GRAD", "RANGE"], 1
    )


def test_flat_window_votes() -> None:
    # σ = 0: no z / Bollinger vote; RSI 100 (no losses) and the range high check vote −1.
    assert votes(_FLAT, _PARAMS) == {
        "Z": 0,
        "SMA": 0,
        "RSI": -1,
        "BB": 0,
        "PCTL": 1,
        "MED": 0,
        "GRAD": 0,
        "RANGE": -1,
    }


def test_rsi_votes_with_its_own_history() -> None:
    # A 5-close window is shorter than RSI's 15 closes; RSI still votes.
    falling = [100 - 0.5 * i for i in range(15)]
    assert votes(falling, SignalConsensusParams(window=5))["RSI"] == 1


def test_overbought_votes_count_against_the_score() -> None:
    ballot = votes(_PULLBACK, _PARAMS)
    assert (ballot["MED"], ballot["GRAD"], ballot["RSI"]) == (1, 1, -1)
    assert sum(ballot.values()) == 1


# Signals ---------------------------------------------------------------------
def test_enters_on_an_oversold_consensus() -> None:
    signal = _signal(_DIP)
    assert signal.action is SignalAction.ENTER_LONG
    assert "score 8" in signal.reason and "RSI +1" in signal.reason


def test_enters_when_the_score_equals_the_consensus() -> None:
    assert _signal(_SHALLOW, params=SignalConsensusParams(consensus=2)).action is (
        SignalAction.ENTER_LONG
    )


def test_does_not_enter_on_a_weak_consensus() -> None:
    assert _signal(_SHALLOW).action is SignalAction.HOLD
    assert _signal(_PULLBACK, params=SignalConsensusParams(consensus=2)).action is (
        SignalAction.HOLD
    )
    assert _signal(_FLAT).action is SignalAction.HOLD


def test_holds_while_in_a_position() -> None:
    assert _signal(_DIP, _LONG).action is SignalAction.HOLD


def test_insufficient_history_holds() -> None:
    assert _signal(_DIP[1:]).action is SignalAction.HOLD


def test_never_signals_short() -> None:
    rising = [100 + i for i in range(15)]
    for closes in (_DIP, _PULLBACK, _FLAT, rising):
        assert _signal(closes).action in {SignalAction.HOLD, SignalAction.ENTER_LONG}
