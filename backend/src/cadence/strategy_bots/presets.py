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
    BotPreset(
        key="atr_band_supertrend_algo9",
        display_name="SuperTrend (Algo 9)",
        description=(
            "SuperTrend over a 20-close window with a 3× ATR band: buys in an up-trend "
            "above the SuperTrend line and exits on a 0.5% take-profit or stop-loss."
        ),
        course_ref="Algo 9",
        strategy_key=StrategyKey.ATR_BAND_TREND,
        strategy_params={"version": "supertrend", "window": 20, "atr_mult": 3.0},
        take_profit_pct=0.005,
        stop_loss_pct=0.005,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="atr_band_keltner_algo21",
        display_name="Keltner Breakout (Algo 21)",
        description=(
            "Keltner channel of a 20-bar SMA ± 1× ATR: buys on a break above the upper "
            "band and exits back below the SMA, with a 0.5% take-profit and 1% stop-loss. "
            "The course script has no drawdown stop; 5% follows the catalog convention."
        ),
        course_ref="Algo 21",
        strategy_key=StrategyKey.ATR_BAND_TREND,
        strategy_params={
            "version": "keltner",
            "window": 20,
            "atr_mult": 1.0,
            "exit_on_midline": True,
        },
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="adx_trend_algo12",
        display_name="ADX Trend Strength (Algo 12)",
        description=(
            "Buys when the 10-bar ADX is above 20 with +DI leading −DI and exits once the "
            "ADX falls back below 20, with a 0.5% take-profit and 1% stop-loss."
        ),
        course_ref="Algo 12",
        strategy_key=StrategyKey.ADX_TREND,
        strategy_params={"period": 10, "threshold": 20.0},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="rolling_reversion_vwap_adx_algo15",
        display_name="VWAP + ADX Reversion (Algo 15)",
        description=(
            "Buys any close below the 20-bar average of typical prices and takes profit "
            "at 0.5%. Instead of a price stop, a losing trade is closed when the ADX "
            "shows a strong downtrend (DX above 20 with −DI leading). The course measures "
            "the ADX over every candle since the start; this preset uses the last 20 bars."
        ),
        course_ref="Algo 15",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
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
        take_profit_pct=0.005,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="macd_momentum_algo10",
        display_name="MACD Momentum (Algo 10)",
        description=(
            "MACD 12 / 26 with a 9-period signal line: buys a bullish cross while the MACD "
            "is above zero and exits on a 0.5% take-profit or 0.5% stop-loss."
        ),
        course_ref="Algo 10",
        strategy_key=StrategyKey.MACD_MOMENTUM,
        strategy_params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
        take_profit_pct=0.005,
        stop_loss_pct=0.005,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="heikin_ashi_algo11",
        display_name="Heikin-Ashi Trend (Algo 11)",
        description=(
            "Buys on a green Heikin-Ashi candle and sells on the first red one, with a "
            "0.5% take-profit and 1% stop-loss."
        ),
        course_ref="Algo 11",
        strategy_key=StrategyKey.HEIKIN_ASHI_TREND,
        strategy_params={"volume_filter": False},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="heikin_ashi_volume_algo37",
        display_name="Heikin-Ashi + Volume (Algo 37)",
        description=(
            "Buys on a green Heikin-Ashi candle only when the bar's volume is above its "
            "20-bar average; sells on a red candle or when volume fades. No take-profit or "
            "stop-loss, as in the course."
        ),
        course_ref="Algo 37",
        strategy_key=StrategyKey.HEIKIN_ASHI_TREND,
        strategy_params={"volume_filter": True, "volume_window": 20},
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="hma_trend_algo19",
        display_name="HMA Trend (Algos 19 / 26)",
        description=(
            "Fast 9 / slow 21 Hull Moving Averages: buys when the fast HMA is above the slow "
            "one and rising, exits on a falling cross below, with a 0.5% take-profit and 1% "
            "stop-loss. Uses the proper HMA (the course script skips its final smoothing); "
            "Algo 26 trades identically."
        ),
        course_ref="Algos 19, 26",
        strategy_key=StrategyKey.HMA_TREND,
        strategy_params={"fast_period": 9, "slow_period": 21},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="ma_ribbon_algo18",
        display_name="MA Ribbon (Algo 18)",
        description=(
            "Buys when the 5, 10 and 20-bar simple moving averages stack upward "
            "(fast > mid > slow), with a 0.5% take-profit and 1% stop-loss."
        ),
        course_ref="Algo 18",
        strategy_key=StrategyKey.MA_RIBBON,
        strategy_params={"fast_period": 5, "mid_period": 10, "slow_period": 20},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="vama_algo30",
        display_name="VAMA (Algo 30)",
        description=(
            "Buys when the close is above the VAMA and sells when it falls back to or below "
            "it, with no take-profit or stop-loss, as in the course. Uses fixed smoothing "
            "(0.20): the course's adaptive formula always resolves to its maximum."
        ),
        course_ref="Algo 30",
        strategy_key=StrategyKey.VAMA,
        strategy_params={
            "lookback": 20,
            "alpha_min": 0.02,
            "alpha_max": 0.2,
            "adaptive": False,
        },
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="rolling_reversion_gradient_algo3",
        display_name="Gradient Convergence (Algo 3)",
        description=(
            "Buys any close below its 5-bar average and sells once the close is back at or "
            "above it — the course's gradient signal, read long-only. No take-profit or "
            "stop-loss, as in the course."
        ),
        course_ref="Algo 3",
        strategy_key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        strategy_params={
            "average_type": "sma",
            "window": 5,
            "distance": "band",
            "entry_threshold": 0.0,
            "exit_threshold": 0.0,
            "entry_z": 1.0,
            "exit_z": 0.2,
            "exit_mode": "revert",
        },
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="price_velocity_algo48",
        display_name="Price Velocity Reversal (Algo 48)",
        description=(
            "Buys a drop of more than 0.2% per bar that is slowing down and sells on the "
            "first up-bar, with a 0.5% take-profit and 1% stop-loss. The course's ₹2 move "
            "on its ₹1,000 price is expressed as 0.2% so it works at any share price."
        ),
        course_ref="Algo 48",
        strategy_key=StrategyKey.PRICE_VELOCITY_REVERSAL,
        strategy_params={"threshold_pct": 0.002},
        take_profit_pct=0.005,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="trend_confirmation_cadence",
        display_name="Trend Confirmation (Cadence)",
        description=(
            "Cadence's own recipe for 5-minute bars: buys when SMA 20 is above SMA 50, the "
            "MACD 12/26/9 histogram is positive and RSI 14 is between 50 and 70; sells when "
            "any of these breaks (RSI below 45). 1% take-profit and 1% stop-loss."
        ),
        course_ref="Cadence — no course algorithm",
        strategy_key=StrategyKey.TREND_CONFIRMATION,
        strategy_params={
            "sma_fast": 20,
            "sma_slow": 50,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "rsi_period": 14,
            "rsi_entry": 50.0,
            "rsi_max": 70.0,
            "rsi_exit": 45.0,
            "use_roc": False,
            "roc_period": 12,
            "use_obv": False,
            "obv_window": 20,
        },
        take_profit_pct=0.01,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="volume_spike_algo34",
        display_name="Volume Spike (Algo 34)",
        description=(
            "Buys a close above the prior 30-bar high on volume over 1.1× the 20-bar "
            "average; sells a close below the prior low on such a spike. No take-profit "
            "or stop-loss bracket."
        ),
        course_ref="Algo 34",
        strategy_key=StrategyKey.VOLUME_BREAKOUT,
        strategy_params={
            "version": "spike",
            "lookback": 30,
            "volume_window": 20,
            "spike_multiplier": 1.1,
        },
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=True,
    ),
    BotPreset(
        key="volume_spike_simple_algo34",
        display_name="Volume Spike — Simple (Algo 34)",
        description=(
            "The simple method: a 30-bar high breakout on any above-average volume, "
            "exiting on a breakdown with above-average volume. No take-profit or "
            "stop-loss bracket."
        ),
        course_ref="Algo 34",
        strategy_key=StrategyKey.VOLUME_BREAKOUT,
        strategy_params={
            "version": "spike",
            "lookback": 30,
            "volume_window": 20,
            "spike_multiplier": 1.0,
        },
        take_profit_pct=None,
        stop_loss_pct=None,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="vroc_breakout_algo46",
        display_name="VROC Breakout (Algo 46)",
        description=(
            "Primes when volume jumps over 40% in 5 bars while price is in a tight range, "
            "then buys the first close above that range; exits when volume falls, with a "
            "2% take-profit and 1% stop-loss."
        ),
        course_ref="Algo 46",
        strategy_key=StrategyKey.VOLUME_BREAKOUT,
        strategy_params={
            "version": "vroc",
            "vroc_lookback": 5,
            "range_lookback": 5,
            "vroc_threshold": 40.0,
            "vroc_surge": 70.0,
            "tight_range_pct": 0.006,
            "prime_window": 10,
        },
        take_profit_pct=0.02,
        stop_loss_pct=0.01,
        drawdown_stop_pct=0.05,
        is_default=False,
    ),
    BotPreset(
        key="chaikin_oscillator_algo45",
        display_name="Chaikin Oscillator (Algo 45)",
        description=(
            "Buys when the 3/5 Chaikin oscillator of accumulation/distribution crosses "
            "above zero and sells when it falls below zero, with a 0.6% take-profit and "
            "1.2% stop-loss."
        ),
        course_ref="Algo 45",
        strategy_key=StrategyKey.VOLUME_BREAKOUT,
        strategy_params={"version": "chaikin", "chaikin_fast": 3, "chaikin_slow": 5},
        take_profit_pct=0.006,
        stop_loss_pct=0.012,
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
