"""Bot preset catalog — fixed, named course-recipe configurations.

A preset binds one registered strategy to the reference-course values for its
parameters and its engine risk controls (take-profit, stop-loss, drawdown
kill-switch). Presets are the vetted starting points the build form opens with and
the only configurations a future AI orchestrator may deploy; manual creation can still
override any value. Capital, traded assets, benchmark, label, and sizing are
deployment choices and deliberately not part of a preset.

Code-defined (like :mod:`.registry`) so presets version with the strategies that
interpret them. Risk values are fractions (``0.01`` = 1%), the same unit as the
session columns. Integrity (valid params, one default per strategy) is asserted by
tests rather than at import time so a bad preset fails CI, not app startup. Keys are
stable: add presets, never rename or reuse a key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cadence.strategy_bots.constants import StrategyKey
from cadence.strategy_bots.errors import UnknownPresetError


@dataclass(frozen=True)
class BotPreset:
    """One named course-recipe configuration for a strategy."""

    key: str
    display_name: str
    description: str
    course_ref: str
    strategy_key: StrategyKey
    strategy_params: Mapping[str, Any]
    take_profit_pct: float | None
    stop_loss_pct: float | None
    drawdown_stop_pct: float
    is_default: bool


_PRESETS: tuple[BotPreset, ...] = (
    BotPreset(
        key="ma_crossover_algo6",
        display_name="MA Crossover (Algo 6)",
        description=(
            "Fast 5 / slow 12 simple-moving-average crossover with a tight 1% "
            "take-profit and 2% stop-loss bracket."
        ),
        course_ref="Algo 6",
        strategy_key=StrategyKey.MA_CROSSOVER,
        strategy_params={"fast_period": 5, "slow_period": 12},
        take_profit_pct=0.01,
        stop_loss_pct=0.02,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="rsi_mean_reversion_algo16",
        display_name="RSI Mean Reversion (Algo 16)",
        description=(
            "Buys when 14-period RSI drops below 30 and exits as it reverts above 50, "
            "with a 0.5% take-profit and 1% stop-loss."
        ),
        course_ref="Algo 16",
        strategy_key=StrategyKey.RSI_MEAN_REVERSION,
        strategy_params={"period": 14, "oversold": 30.0, "exit_level": 50.0},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="donchian_turtle_algo25",
        display_name="Turtle Breakout (Algo 25)",
        description=(
            "Turtle rolling channel: enters above the prior 20-bar high and exits "
            "below the prior 10-bar low. No take-profit or stop-loss bracket."
        ),
        course_ref="Algo 25",
        strategy_key=StrategyKey.DONCHIAN_BREAKOUT,
        strategy_params={"version": "turtle", "entry_period": 20, "exit_period": 10},
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="donchian_smart_range_algo8",
        display_name="Smart Range Breakout (Algo 8)",
        description=(
            "Locked 20-bar channel padded by 0.5x ATR; holds while in a trade and "
            "exits on the 0.5% take-profit / 2% stop-loss bracket."
        ),
        course_ref="Algo 8",
        strategy_key=StrategyKey.DONCHIAN_BREAKOUT,
        strategy_params={
            "version": "locked",
            "channel_period": 20,
            "atr_padding_mult": 0.5,
        },
        take_profit_pct=0.005,
        stop_loss_pct=0.02,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="rolling_reversion_sma_band_algo5",
        display_name="SMA Band Reversion (Algo 5)",
        description=(
            "Buys when the close is more than 1% below its 20-bar simple average and "
            "exits once it is back within 0.5% of it, with a 2% stop-loss."
        ),
        course_ref="Algo 5",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
            "average_type": "sma",
            "window": 20,
            "distance": "band",
            "entry_threshold": 0.01,
            "exit_threshold": 0.005,
            "entry_z": 1.0,
            "exit_z": 0.2,
            "exit_mode": "revert",
        },
        take_profit_pct=None,
        stop_loss_pct=0.02,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="rolling_reversion_zscore_algo4",
        display_name="Z-Score Reversion (Algo 4)",
        description=(
            "Buys when the close is more than 1 standard deviation below its 20-bar "
            "average and exits once the z-score is back above -0.2, with a 2% stop-loss."
        ),
        course_ref="Algo 4",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
            "average_type": "sma",
            "window": 20,
            "distance": "zscore",
            "entry_threshold": 0.01,
            "exit_threshold": 0.005,
            "entry_z": 1.0,
            "exit_z": 0.2,
            "exit_mode": "revert",
        },
        take_profit_pct=None,
        stop_loss_pct=0.02,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="rolling_reversion_mean_cross_algo14",
        display_name="Mean Cross Reversion (Algo 14)",
        description=(
            "Buys on any close below its 60-bar average and exits on the 0.5% "
            "take-profit / 1% stop-loss bracket."
        ),
        course_ref="Algo 14",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
            "average_type": "sma",
            "window": 60,
            "distance": "band",
            "entry_threshold": 0.0,
            "exit_threshold": 0.005,
            "entry_z": 1.0,
            "exit_z": 0.2,
            "exit_mode": "bracket",
        },
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="rolling_reversion_vwap_cross_algo39",
        display_name="VWAP Cross Reversion (Algo 39)",
        description=(
            "Buys on any close below its 60-bar volume-weighted average price and "
            "exits on the 0.5% take-profit / 1% stop-loss bracket."
        ),
        course_ref="Algo 39",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
            "average_type": "vwap",
            "window": 60,
            "distance": "band",
            "entry_threshold": 0.0,
            "exit_threshold": 0.005,
            "entry_z": 1.0,
            "exit_z": 0.2,
            "exit_mode": "bracket",
        },
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
)

_BY_KEY: dict[str, BotPreset] = {preset.key: preset for preset in _PRESETS}


def list_presets() -> list[BotPreset]:
    """Return every preset in catalog order."""
    return list(_PRESETS)


def get_preset(key: str) -> BotPreset:
    """Resolve a preset by key, or raise ``UnknownPresetError``."""
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        raise UnknownPresetError(key) from exc
