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
