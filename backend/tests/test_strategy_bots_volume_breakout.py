"""Unit tests for the Volume Breakout strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.registry import get_strategy
from cadence.strategy_bots.strategy import Bar, PositionView, SignalAction, Strategy
from cadence.strategy_bots.volume_breakout import (
    VolumeBreakoutParams,
    VolumeBreakoutStrategy,
    accumulation_distribution,
    chaikin_oscillator,
    vroc,
)
from cadence.technical_indicators import series

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=100.0)
_STRATEGY = VolumeBreakoutStrategy()
_SPIKE = VolumeBreakoutParams(version="spike", lookback=5, volume_window=3, spike_multiplier=1.5)
_VROC = VolumeBreakoutParams(version="vroc", vroc_lookback=2, range_lookback=3, prime_window=3)
_CHAIKIN = VolumeBreakoutParams(version="chaikin", chaikin_fast=2, chaikin_slow=3)


def _bars(
    closes: Sequence[float],
    volumes: Sequence[float] | None = None,
    *,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
) -> list[Bar]:
    volumes = volumes or [1_000.0] * len(closes)
    highs = highs or closes
    lows = lows or closes
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        for i, (c, v, h, lo) in enumerate(zip(closes, volumes, highs, lows, strict=True))
    ]


def _action(bars: list[Bar], params: VolumeBreakoutParams, position: PositionView | None = None):
    return _STRATEGY.evaluate(bars, position, params).action


# Registration & params -------------------------------------------------------
def test_registered_and_satisfies_protocol() -> None:
    registration = get_strategy(StrategyKey.VOLUME_BREAKOUT.value)
    assert registration.display_name == "Volume Breakout"
    assert isinstance(registration.strategy, Strategy)
    assert registration.params_schema is VolumeBreakoutParams


def test_default_params_match_the_course() -> None:
    params = VolumeBreakoutParams()
    assert params.version == "spike"
    assert (params.lookback, params.volume_window, params.spike_multiplier) == (30, 20, 1.1)
    assert (params.vroc_lookback, params.range_lookback, params.prime_window) == (5, 5, 10)
    assert (params.vroc_threshold, params.vroc_surge, params.tight_range_pct) == (40, 70, 0.006)
    assert (params.chaikin_fast, params.chaikin_slow) == (3, 5)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        (VolumeBreakoutParams(version="spike"), 30),
        (VolumeBreakoutParams(version="spike", lookback=10, volume_window=25), 25),
        (VolumeBreakoutParams(version="vroc"), 16),
        (VolumeBreakoutParams(version="chaikin"), 16),
    ],
)
def test_required_history_per_version(params: VolumeBreakoutParams, expected: int) -> None:
    assert params.required_history == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chaikin_fast": 5, "chaikin_slow": 5},
        {"vroc_threshold": 80, "vroc_surge": 70},
        {"lookback": 2},
        {"spike_multiplier": 0},
        {"tight_range_pct": 0},
        {"version": "short"},
        {"unknown": 1},
    ],
)
def test_invalid_params_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VolumeBreakoutParams(**kwargs)  # type: ignore[arg-type]


def test_rejects_foreign_params() -> None:
    from cadence.strategy_bots.vama import VamaParams

    with pytest.raises(TypeError):
        _STRATEGY.evaluate(_bars([1.0] * 40), None, VamaParams())


@pytest.mark.parametrize("params", [_SPIKE, _VROC, _CHAIKIN])
def test_insufficient_history_holds(params: VolumeBreakoutParams) -> None:
    bars = _bars([100.0] * (params.required_history - 1))
    assert _action(bars, params) is SignalAction.HOLD
    assert _action(bars, params, _LONG) is SignalAction.HOLD


# Spike -----------------------------------------------------------------------
_PRIOR = [10.0, 11.0, 10.5, 11.0]


def test_spike_enters_on_volume_confirmed_breakout() -> None:
    # Average of the last 3 volumes (100, 100, 300) is 166.7; 300 > 1.5 × 166.7.
    bars = _bars([*_PRIOR, 12.0], [100, 100, 100, 100, 300])
    assert _action(bars, _SPIKE) is SignalAction.ENTER_LONG


def test_spike_ignores_breakout_without_volume() -> None:
    # 200 is not strictly above 1.5 × 133.3 = 200.
    bars = _bars([*_PRIOR, 12.0], [100, 100, 100, 100, 200])
    assert _action(bars, _SPIKE) is SignalAction.HOLD


def test_spike_ignores_spike_without_breakout() -> None:
    bars = _bars([*_PRIOR, 11.0], [100, 100, 100, 100, 300])
    assert _action(bars, _SPIKE) is SignalAction.HOLD


def test_spike_exits_on_volume_confirmed_breakdown() -> None:
    bars = _bars([*_PRIOR, 9.0], [100, 100, 100, 100, 300])
    assert _action(bars, _SPIKE, _LONG) is SignalAction.EXIT


@pytest.mark.parametrize(
    ("close", "volume"),
    [(9.0, 100.0), (12.0, 300.0), (10.5, 300.0)],
)
def test_spike_holds_position_otherwise(close: float, volume: float) -> None:
    bars = _bars([*_PRIOR, close], [100, 100, 100, 100, volume])
    assert _action(bars, _SPIKE, _LONG) is SignalAction.HOLD


# VROC ------------------------------------------------------------------------
def test_vroc_helper() -> None:
    volumes = [100.0, 50.0, 150.0, 0.0, 10.0]
    assert vroc(volumes, 2, 2) == pytest.approx(50.0)
    assert vroc(volumes, 1, 2) is None
    assert vroc(volumes, 4, 1) is None  # earlier volume 0


def _vroc_case(
    *, range_closes: Sequence[float], after: float, last: float, surge_volume: float
) -> list[Bar]:
    """Eight bars; bar 5 is the candidate priming bar (VROC vs bar 3)."""
    closes = [100.0, 100.0, 100.0, *range_closes, after, last]
    volumes = [100.0, 100.0, 100.0, 100.0, 100.0, surge_volume, 100.0, 100.0]
    return _bars(closes, volumes)


def test_vroc_enters_on_first_breakout_after_tight_priming() -> None:
    bars = _vroc_case(
        range_closes=[100.0, 100.2, 100.1], after=100.1, last=101.0, surge_volume=150.0
    )
    assert _action(bars, _VROC) is SignalAction.ENTER_LONG


def test_vroc_surge_primes_without_tight_range() -> None:
    bars = _vroc_case(
        range_closes=[100.0, 102.0, 101.0], after=101.0, last=103.0, surge_volume=200.0
    )
    assert _action(bars, _VROC) is SignalAction.ENTER_LONG


def test_vroc_threshold_without_tight_range_does_not_prime() -> None:
    bars = _vroc_case(
        range_closes=[100.0, 102.0, 101.0], after=101.0, last=103.0, surge_volume=150.0
    )
    assert _action(bars, _VROC) is SignalAction.HOLD


def test_vroc_does_not_reenter_on_an_already_broken_range() -> None:
    bars = _vroc_case(
        range_closes=[100.0, 100.2, 100.1], after=100.5, last=101.0, surge_volume=150.0
    )
    signal = _STRATEGY.evaluate(bars, None, _VROC)
    assert signal.action is SignalAction.HOLD
    assert "already broken" in signal.reason


def test_vroc_waits_below_the_primed_range() -> None:
    bars = _vroc_case(
        range_closes=[100.0, 100.2, 100.1], after=100.1, last=100.15, surge_volume=150.0
    )
    assert _action(bars, _VROC) is SignalAction.HOLD


def test_vroc_holds_without_priming() -> None:
    bars = _bars([100.0] * 7 + [105.0], [100.0] * 8)
    assert _action(bars, _VROC) is SignalAction.HOLD


def test_vroc_ignores_stale_priming() -> None:
    # Bar 3 primes (VROC 100% vs bar 1) but the window only covers bars 5–7.
    closes = [100.0, 100.0, 100.0, 100.1, 100.0, 100.0, 100.0, 100.0, 101.0]
    volumes = [100.0, 100.0, 100.0, 200.0, 200.0, 200.0, 200.0, 200.0, 200.0]
    assert _action(_bars(closes, volumes), _VROC) is SignalAction.HOLD


def test_vroc_non_positive_volume_cannot_prime() -> None:
    closes = [100.0, 100.0, 100.0, 100.0, 100.2, 100.1, 100.1, 101.0]
    volumes = [100.0, 100.0, 100.0, 0.0, 100.0, 150.0, 100.0, 100.0]
    assert _action(_bars(closes, volumes), _VROC) is SignalAction.HOLD


@pytest.mark.parametrize(
    ("last_volume", "expected"),
    [(100.0, SignalAction.EXIT), (250.0, SignalAction.HOLD), (200.0, SignalAction.HOLD)],
)
def test_vroc_exits_when_volume_momentum_reverses(
    last_volume: float, expected: SignalAction
) -> None:
    volumes = [100.0] * 5 + [200.0, 100.0, last_volume]
    assert _action(_bars([100.0] * 8, volumes), _VROC, _LONG) is expected


def test_vroc_holding_with_undefined_vroc_holds() -> None:
    volumes = [100.0] * 5 + [0.0, 100.0, 100.0]
    assert _action(_bars([100.0] * 8, volumes), _VROC, _LONG) is SignalAction.HOLD


# Chaikin ---------------------------------------------------------------------
def test_accumulation_distribution() -> None:
    bars = _bars(
        [10.0, 8.0, 9.0, 5.0],
        [100.0, 100.0, 100.0, 100.0],
        highs=[10.0, 10.0, 10.0, 5.0],
        lows=[8.0, 8.0, 8.0, 5.0],
    )
    # Close at the high (+1), at the low (−1), mid-range (0), and a flat bar (0).
    assert accumulation_distribution(bars) == [100.0, 0.0, 0.0, 0.0]


def test_oscillator_is_offset_invariant() -> None:
    adl = pd.Series([float(v) for v in [5, 3, 8, 1, 9, 4, 7, 2, 6, 10]])
    base = series.ema(adl, 2) - series.ema(adl, 3)
    shifted = series.ema(adl + 1_000.0, 2) - series.ema(adl + 1_000.0, 3)
    assert shifted.iloc[-1] == pytest.approx(base.iloc[-1])


def _chaikin_bars(flows: Sequence[int]) -> list[Bar]:
    """Bars closing at their high (+1) or low (−1) with equal volume."""
    closes = [10.0 if f > 0 else 8.0 for f in flows]
    return _bars(closes, [100.0] * len(flows), highs=[10.0] * len(flows), lows=[8.0] * len(flows))


def test_chaikin_enters_on_zero_cross_up() -> None:
    bars = _chaikin_bars([-1] * 10 + [1, 1])
    oscillator = chaikin_oscillator(bars, 2, 3)
    assert oscillator.iloc[-2] <= 0 < oscillator.iloc[-1]
    assert _action(bars, _CHAIKIN) is SignalAction.ENTER_LONG


def test_chaikin_holds_without_cross() -> None:
    assert _action(_chaikin_bars([1] * 11), _CHAIKIN) is SignalAction.HOLD
    assert _action(_chaikin_bars([-1] * 11), _CHAIKIN) is SignalAction.HOLD
    # Already above zero on the previous bar: no fresh cross.
    assert _action(_chaikin_bars([-1] * 10 + [1, 1, 1]), _CHAIKIN) is SignalAction.HOLD


def test_chaikin_exits_below_zero() -> None:
    assert _action(_chaikin_bars([1] * 10 + [-1, -1]), _CHAIKIN, _LONG) is SignalAction.EXIT


def test_chaikin_holds_position_above_zero() -> None:
    assert _action(_chaikin_bars([1] * 11), _CHAIKIN, _LONG) is SignalAction.HOLD


def test_never_signals_short() -> None:
    falling = _chaikin_bars([1] * 5 + [-1] * 6)
    for params in (_SPIKE, _VROC, _CHAIKIN):
        assert _STRATEGY.evaluate(falling, None, params).action in {
            SignalAction.HOLD,
            SignalAction.ENTER_LONG,
        }
