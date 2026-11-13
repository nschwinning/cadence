"""Integrity tests for the bot preset catalog.

Pure (no DB): every preset must reference a registered strategy with valid params,
keys must be unique, each registered strategy must have exactly one default preset,
and the seeded presets must reproduce the reference-course recipes.
"""

from __future__ import annotations

from collections import Counter

import pytest

from cadence.strategy_bots import presets, registry
from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.errors import UnknownPresetError


def test_preset_keys_are_unique() -> None:
    keys = [preset.key for preset in presets.list_presets()]
    assert len(keys) == len(set(keys))


def test_every_preset_has_valid_params_for_its_strategy() -> None:
    for preset in presets.list_presets():
        registration = registry.get_strategy(preset.strategy_key.value)
        registration.parse_params(preset.strategy_params)


def test_exactly_one_default_per_registered_strategy() -> None:
    defaults = Counter(
        preset.strategy_key for preset in presets.list_presets() if preset.is_default
    )
    for registration in registry.list_strategies():
        assert defaults[registration.key] == 1, registration.key


def test_get_preset_unknown_key_raises() -> None:
    with pytest.raises(UnknownPresetError):
        presets.get_preset("nope")


@pytest.mark.parametrize(
    ("key", "strategy", "params", "tp", "sl", "dd", "is_default"),
    [
        (
            "ma_crossover_algo6",
            StrategyKey.MA_CROSSOVER,
            {"fast_period": 5, "slow_period": 12},
            0.01,
            0.02,
            0.05,
            True,
        ),
        (
            "rsi_mean_reversion_algo16",
            StrategyKey.RSI_MEAN_REVERSION,
            {"period": 14, "oversold": 30.0, "exit_level": 50.0},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "donchian_turtle_algo25",
            StrategyKey.DONCHIAN_BREAKOUT,
            {"version": "turtle", "entry_period": 20, "exit_period": 10},
            None,
            None,
            0.05,
            True,
        ),
        (
            "donchian_smart_range_algo8",
            StrategyKey.DONCHIAN_BREAKOUT,
            {"version": "locked", "channel_period": 20, "atr_padding_mult": 0.5},
            0.005,
            0.02,
            0.05,
            False,
        ),
        (
            "rolling_reversion_sma_band_algo5",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {"average_type": "sma", "window": 20, "distance": "band", "entry_threshold": 0.01, "exit_threshold": 0.005, "entry_z": 1.0, "exit_z": 0.2, "exit_mode": "revert"},
            None,
            0.02,
            0.05,
            True,
        ),
        (
            "rolling_reversion_zscore_algo4",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {"average_type": "sma", "window": 20, "distance": "zscore", "entry_threshold": 0.01, "exit_threshold": 0.005, "entry_z": 1.0, "exit_z": 0.2, "exit_mode": "revert"},
            None,
            0.02,
            0.05,
            False,
        ),
        (
            "rolling_reversion_mean_cross_algo14",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {"average_type": "sma", "window": 60, "distance": "band", "entry_threshold": 0.0, "exit_threshold": 0.005, "entry_z": 1.0, "exit_z": 0.2, "exit_mode": "bracket"},
            0.005,
            0.01,
            0.05,
            False,
        ),
        (
            "rolling_reversion_vwap_cross_algo39",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {"average_type": "vwap", "window": 60, "distance": "band", "entry_threshold": 0.0, "exit_threshold": 0.005, "entry_z": 1.0, "exit_z": 0.2, "exit_mode": "bracket"},
            0.005,
            0.01,
            0.05,
            False,
        ),
        (
            "rolling_reversion_gradient_algo3",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {"average_type": "sma", "window": 5, "distance": "band", "entry_threshold": 0.0, "exit_threshold": 0.0, "entry_z": 1.0, "exit_z": 0.2, "exit_mode": "revert"},
            None,
            None,
            0.05,
            False,
        ),
        (
            "bayesian_trend_algo33",
            StrategyKey.BAYESIAN_TREND,
            {"drift": 0.001, "trend_sigma": 0.002, "flat_sigma": 0.0008, "threshold": 0.6, "replay_bars": 20},
            None,
            None,
            0.05,
            True,
        ),
        (
            "signal_consensus_algo43",
            StrategyKey.SIGNAL_CONSENSUS,
            {"window": 10, "consensus": 3, "rsi_period": 14, "bb_k": 2.0},
            0.005,
            0.003,
            0.05,
            True,
        ),
        (
            "volatility_regime_algo20",
            StrategyKey.VOLATILITY_REGIME,
            {"atr_window": 20, "sma_period": 20, "baseline_bars": 100, "reversion_deviation": 0.0},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "volume_spike_algo34",
            StrategyKey.VOLUME_BREAKOUT,
            {"version": "spike", "lookback": 30, "volume_window": 20, "spike_multiplier": 1.1},
            None,
            None,
            0.05,
            True,
        ),
        (
            "volume_spike_simple_algo34",
            StrategyKey.VOLUME_BREAKOUT,
            {"version": "spike", "lookback": 30, "volume_window": 20, "spike_multiplier": 1.0},
            None,
            None,
            0.05,
            False,
        ),
        (
            "vroc_breakout_algo46",
            StrategyKey.VOLUME_BREAKOUT,
            {"version": "vroc", "vroc_lookback": 5, "range_lookback": 5, "vroc_threshold": 40.0, "vroc_surge": 70.0, "tight_range_pct": 0.006, "prime_window": 10},
            0.02,
            0.01,
            0.05,
            False,
        ),
        (
            "chaikin_oscillator_algo45",
            StrategyKey.VOLUME_BREAKOUT,
            {"version": "chaikin", "chaikin_fast": 3, "chaikin_slow": 5},
            0.006,
            0.012,
            0.05,
            False,
        ),
        (
            "trend_confirmation_cadence",
            StrategyKey.TREND_CONFIRMATION,
            {"sma_fast": 20, "sma_slow": 50, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_entry": 50.0, "rsi_max": 70.0, "rsi_exit": 45.0, "use_roc": False, "roc_period": 12, "use_obv": False, "obv_window": 20},
            0.01,
            0.01,
            0.05,
            True,
        ),
        (
            "price_velocity_algo48",
            StrategyKey.PRICE_VELOCITY_REVERSAL,
            {"threshold_pct": 0.002},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "vama_algo30",
            StrategyKey.VAMA,
            {"lookback": 20, "alpha_min": 0.02, "alpha_max": 0.2, "adaptive": False},
            None,
            None,
            0.05,
            True,
        ),
        (
            "ma_ribbon_algo18",
            StrategyKey.MA_RIBBON,
            {"fast_period": 5, "mid_period": 10, "slow_period": 20},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "hma_trend_algo19",
            StrategyKey.HMA_TREND,
            {"fast_period": 9, "slow_period": 21},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "heikin_ashi_algo11",
            StrategyKey.HEIKIN_ASHI_TREND,
            {"volume_filter": False},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "heikin_ashi_volume_algo37",
            StrategyKey.HEIKIN_ASHI_TREND,
            {"volume_filter": True, "volume_window": 20},
            None,
            None,
            0.05,
            False,
        ),
        (
            "macd_momentum_algo10",
            StrategyKey.MACD_MOMENTUM,
            {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            0.005,
            0.005,
            0.05,
            True,
        ),
        (
            "adx_trend_algo12",
            StrategyKey.ADX_TREND,
            {"period": 10, "threshold": 20.0},
            0.005,
            0.01,
            0.05,
            True,
        ),
        (
            "rolling_reversion_vwap_adx_algo15",
            StrategyKey.ROLLING_AVERAGE_REVERSION,
            {
                "average_type": "typical",
                "window": 20,
                "distance": "band",
                "entry_threshold": 0.0,
                "exit_threshold": 0.005,
                "entry_z": 1.0,
                "exit_z": 0.2,
                "exit_mode": "bracket",
                "adx_exit": True,
                "adx_lookback": 20,
                "adx_threshold": 20.0,
            },
            0.005,
            None,
            0.05,
            False,
        ),
        (
            "atr_band_supertrend_algo9",
            StrategyKey.ATR_BAND_TREND,
            {"version": "supertrend", "window": 20, "atr_mult": 3.0},
            0.005,
            0.005,
            0.05,
            True,
        ),
        (
            "atr_band_keltner_algo21",
            StrategyKey.ATR_BAND_TREND,
            {"version": "keltner", "window": 20, "atr_mult": 1.0, "exit_on_midline": True},
            0.005,
            0.01,
            0.05,
            False,
        ),
    ],
)
def test_course_recipes(
    key: str,
    strategy: StrategyKey,
    params: dict[str, object],
    tp: float | None,
    sl: float | None,
    dd: float,
    is_default: bool,
) -> None:
    preset = presets.get_preset(key)
    assert preset.strategy_key is strategy
    assert dict(preset.strategy_params) == params
    assert preset.take_profit_pct == tp
    assert preset.stop_loss_pct == sl
    assert preset.drawdown_stop_pct == dd
    assert preset.is_default is is_default
