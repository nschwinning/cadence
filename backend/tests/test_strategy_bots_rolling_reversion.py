"""Unit tests for the Rolling-Average Reversion strategy (pure, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cadence.strategy_bots.rolling_average_reversion import (
    RollingAverageReversionParams,
    RollingAverageReversionStrategy,
    _average,
    _price_series,
)
from cadence.strategy_bots.strategy import (
    Bar,
    PositionView,
    SignalAction,
    Strategy,
)

_START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
_LONG = PositionView(quantity=10, avg_price=95.0)
_STRATEGY = RollingAverageReversionStrategy()


def _bars(
    closes: Sequence[float],
    *,
    volumes: Sequence[float] | None = None,
    high_pad: float = 0.0,
) -> list[Bar]:
    """Bars with the given closes; highs padded by ``high_pad``, lows at the close."""
    vols = list(volumes) if volumes is not None else [1_000.0] * len(closes)
    return [
        Bar(
            timestamp=_START + timedelta(minutes=5 * i),
            open=close,
            high=close + high_pad,
            low=close,
            close=close,
            volume=vols[i],
        )
        for i, close in enumerate(closes)
    ]


def _params(**overrides: object) -> RollingAverageReversionParams:
    base: dict[str, object] = {"window": 5}
    base.update(overrides)
    return RollingAverageReversionParams.model_validate(base)


def test_satisfies_strategy_protocol() -> None:
    assert isinstance(_STRATEGY, Strategy)


# Band ------------------------------------------------------------------------
def test_band_entry_below_the_average_while_flat() -> None:
    # avg 99, close 95 → −4.04% < −1%.
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 95]), None, _params())
    assert signal.action is SignalAction.ENTER_LONG
    assert "below" in signal.reason


def test_band_close_within_band_holds_while_flat() -> None:
    # avg 99.9, close 99.5 → −0.4%, inside the 1% entry band.
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 99.5]), None, _params())
    assert signal.action is SignalAction.HOLD


def test_zero_band_enters_on_a_bare_cross() -> None:
    params = _params(entry_threshold=0.0, exit_mode="bracket")
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 99.9]), None, params)
    assert signal.action is SignalAction.ENTER_LONG


def test_zero_band_holds_at_the_average() -> None:
    params = _params(entry_threshold=0.0, exit_mode="bracket")
    signal = _STRATEGY.evaluate(_bars([100] * 5), None, params)
    assert signal.action is SignalAction.HOLD


# Z-score ---------------------------------------------------------------------
def test_zscore_entry_while_flat() -> None:
    # mean 99, population std ≈ 2.098 → z ≈ −1.91 < −1.0.
    params = _params(distance="zscore")
    signal = _STRATEGY.evaluate(_bars([100, 101, 99, 100, 95]), None, params)
    assert signal.action is SignalAction.ENTER_LONG
    assert "z-score" in signal.reason


def test_zscore_within_band_holds_while_flat() -> None:
    params = _params(distance="zscore")
    signal = _STRATEGY.evaluate(_bars([100, 101, 99, 100, 100]), None, params)
    assert signal.action is SignalAction.HOLD


def test_zscore_revert_exit_while_long() -> None:
    params = _params(distance="zscore")
    signal = _STRATEGY.evaluate(_bars([100, 101, 99, 100, 100]), _LONG, params)
    assert signal.action is SignalAction.EXIT


# Exit modes ------------------------------------------------------------------
def test_revert_exit_once_back_within_the_exit_band() -> None:
    # avg 99.96, close 99.8 → −0.16% ≥ −0.5%.
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 99.8]), _LONG, _params())
    assert signal.action is SignalAction.EXIT


def test_revert_exit_on_overshoot_above_the_average() -> None:
    # The course's abs(deviation) test would not exit here; the long-only port does.
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 105]), _LONG, _params())
    assert signal.action is SignalAction.EXIT


def test_revert_holds_while_still_below_the_exit_level() -> None:
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 95]), _LONG, _params())
    assert signal.action is SignalAction.HOLD


def test_bracket_holds_while_long_wherever_the_close_sits() -> None:
    params = _params(entry_threshold=0.0, exit_mode="bracket")
    for closes in ([100, 100, 100, 100, 110], [100, 100, 100, 100, 90]):
        signal = _STRATEGY.evaluate(_bars(closes), _LONG, params)
        assert signal.action is SignalAction.HOLD
        assert "bracket" in signal.reason


def test_flat_with_close_far_above_the_average_never_shorts() -> None:
    signal = _STRATEGY.evaluate(_bars([100, 100, 100, 100, 150]), None, _params())
    assert signal.action is SignalAction.HOLD


# Average types ---------------------------------------------------------------
def test_average_types_use_their_own_price_series() -> None:
    bars = _bars([110, 100, 100, 100, 99], volumes=[1, 1000, 1000, 1000, 1000], high_pad=6)

    sma = _average(bars, _price_series(bars, "sma"), "sma")
    typical = _average(bars, _price_series(bars, "typical"), "typical")
    vwap = _average(bars, _price_series(bars, "vwap"), "vwap")

    assert sma == pytest.approx(101.8)
    # Typical = (close + 6 + close) / 3 = close + 2 per bar.
    assert typical == pytest.approx(103.8)
    assert vwap == pytest.approx((110 * 1 + 100 * 3000 + 99 * 1000) / 4001)


def test_average_type_changes_the_signal_on_the_same_bars() -> None:
    # Heavy volume on the latest bars pulls the VWAP down to ~99.75 (−0.75%: inside the
    # 1% band) while the equal-weight SMA of 101.8 puts the close 2.75% below.
    bars = _bars([110, 100, 100, 100, 99], volumes=[1, 1000, 1000, 1000, 1000])

    sma_signal = _STRATEGY.evaluate(bars, None, _params(average_type="sma"))
    vwap_signal = _STRATEGY.evaluate(bars, None, _params(average_type="vwap"))

    assert sma_signal.action is SignalAction.ENTER_LONG
    assert vwap_signal.action is SignalAction.HOLD


# Undefined measures / history -------------------------------------------------
def test_vwap_with_zero_volume_holds() -> None:
    bars = _bars([100, 100, 100, 100, 90], volumes=[0] * 5)
    signal = _STRATEGY.evaluate(bars, None, _params(average_type="vwap"))
    assert signal.action is SignalAction.HOLD
    assert "volume" in signal.reason


def test_zscore_with_zero_dispersion_holds() -> None:
    signal = _STRATEGY.evaluate(_bars([100] * 5), None, _params(distance="zscore"))
    assert signal.action is SignalAction.HOLD
    assert "dispersion" in signal.reason


def test_insufficient_history_holds() -> None:
    signal = _STRATEGY.evaluate(_bars([100, 100, 90]), None, _params())
    assert signal.action is SignalAction.HOLD
    assert "insufficient history" in signal.reason


def test_window_uses_only_the_latest_bars() -> None:
    # A huge early close outside the 5-bar window must not move the average.
    bars = _bars([1_000, 100, 100, 100, 100, 99.5])
    signal = _STRATEGY.evaluate(bars, None, _params())
    assert signal.action is SignalAction.HOLD


# Params ----------------------------------------------------------------------
def test_defaults_match_the_course_sma_band_recipe() -> None:
    params = RollingAverageReversionParams()
    assert params.model_dump() == {
        "average_type": "sma",
        "window": 20,
        "distance": "band",
        "entry_threshold": 0.01,
        "exit_threshold": 0.005,
        "entry_z": 1.0,
        "exit_z": 0.2,
        "exit_mode": "revert",
    }
    assert params.required_history == 20


@pytest.mark.parametrize(
    "overrides",
    [
        {"average_type": "ema"},
        {"distance": "atr"},
        {"exit_mode": "trail"},
        {"window": 1},
        {"entry_threshold": -0.01},
        {"exit_z": -0.1},
        {"entry_threshold": 1.0},
        {"unknown_field": 1},
        # Revert mode needs the exit level strictly above the entry level.
        {"entry_threshold": 0.01, "exit_threshold": 0.01},
        {"entry_threshold": 0.0},
        {"distance": "zscore", "entry_z": 1.0, "exit_z": 1.5},
    ],
)
def test_invalid_params_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RollingAverageReversionParams.model_validate(overrides)


def test_bracket_mode_skips_the_ordering_check() -> None:
    params = RollingAverageReversionParams.model_validate(
        {"entry_threshold": 0.0, "exit_threshold": 0.005, "exit_mode": "bracket"}
    )
    assert params.entry_threshold == 0.0
