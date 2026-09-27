"""Unit tests for the technical-indicator compute engine."""

from __future__ import annotations

from datetime import date, timedelta

from cadence.assets.market_data import HistoryBar
from cadence.technical_indicators.compute import compute_snapshot


def _bars(closes: list[float], *, volumes: list[float] | None = None) -> list[HistoryBar]:
    start = date(2020, 1, 1)
    vols = volumes if volumes is not None else [1_000_000.0] * len(closes)
    return [
        HistoryBar(date=start + timedelta(days=i), close=close, volume=vol)
        for i, (close, vol) in enumerate(zip(closes, vols, strict=True))
    ]


def _steady_uptrend(n: int = 320) -> list[float]:
    # Compounding uptrend so every MA structure and momentum condition passes.
    return [100.0 * (1.003**i) for i in range(n)]


def _steady_downtrend(n: int = 320) -> list[float]:
    return [300.0 * (0.997**i) for i in range(n)]


def test_empty_bars_returns_none() -> None:
    assert compute_snapshot([]) is None


def test_insufficient_history_yields_absent_values_and_gate_fails() -> None:
    snap = compute_snapshot(_bars(_steady_uptrend(30)))
    assert snap is not None
    # SMA200 needs 200 bars; absent here.
    assert snap.sma_200 is None
    assert snap.roc_120 is None
    # Gate reads absent inputs as fail.
    assert snap.gate.regime_pass is False
    assert snap.gate.gate_pass is False


def test_uptrend_passes_the_gate() -> None:
    snap = compute_snapshot(_bars(_steady_uptrend()))
    assert snap is not None
    assert snap.sma_50 is not None and snap.sma_200 is not None
    assert snap.close is not None and snap.close > snap.sma_200
    assert snap.gate.regime_pass is True
    assert snap.gate.momentum_pass is True
    assert snap.gate.gate_pass is True


def test_downtrend_fails_the_gate() -> None:
    snap = compute_snapshot(_bars(_steady_downtrend()))
    assert snap is not None
    assert snap.gate.regime_pass is False
    assert snap.gate.momentum_pass is False
    assert snap.gate.gate_pass is False


def test_reversal_flags_present_in_downtrend() -> None:
    snap = compute_snapshot(_bars(_steady_downtrend()))
    assert snap is not None
    flags = snap.reversal_flags
    # A sustained downtrend has a declining histogram and a negative MA slope.
    assert flags.macd_hist_rollover is True
    assert flags.sma200_slope_flattening is True


def test_uptrend_has_no_slope_flattening_flag() -> None:
    snap = compute_snapshot(_bars(_steady_uptrend()))
    assert snap is not None
    assert snap.reversal_flags.sma200_slope_flattening is False


def test_macd_and_rsi_rollover_when_momentum_turns_down() -> None:
    # A long rise then a single sharp down bar rolls the histogram and RSI over.
    up = _steady_uptrend(300)
    closes = up + [up[-1] * 0.85]
    snap = compute_snapshot(_bars(closes))
    assert snap is not None
    assert snap.reversal_flags.macd_hist_rollover is True
    assert snap.reversal_flags.rsi_rollover is True


def test_obv_change_tracks_volume_direction() -> None:
    snap = compute_snapshot(_bars(_steady_uptrend()))
    assert snap is not None
    # Every up day adds volume to OBV → positive 20d change and obv_rising.
    assert snap.obv_change_20d is not None and snap.obv_change_20d > 0.0
    assert snap.gate.obv_rising is True
