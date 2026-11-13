"""Strategy registry — layer 3 of the execution model.

Maps each :class:`~cadence.strategy_bots.constants.StrategyKey` to its pure
strategy implementation, its parameter schema, and (derived from validated params)
the number of historical bars it needs. The tick runner resolves a session's
strategy here to size its bar fetch and validate its parameters; session creation
resolves it to reject an unregistered key and validate the supplied params. Adding
a strategy is additive: implement it, then register one entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from cadence.strategy_bots.adx_trend import AdxTrendParams, AdxTrendStrategy
from cadence.strategy_bots.atr_band_trend import AtrBandTrendParams, AtrBandTrendStrategy
from cadence.strategy_bots.constants import (
    STRATEGY_DISPLAY_NAMES,
    STRATEGY_EXPLANATIONS,
    StrategyKey,
)
from cadence.strategy_bots.donchian_breakout import (
    DonchianBreakoutParams,
    DonchianBreakoutStrategy,
)
from cadence.strategy_bots.errors import (
    InvalidStrategyParamsError,
    UnknownStrategyError,
)
from cadence.strategy_bots.heikin_ashi_trend import (
    HeikinAshiTrendParams,
    HeikinAshiTrendStrategy,
)
from cadence.strategy_bots.hma_trend import HmaTrendParams, HmaTrendStrategy
from cadence.strategy_bots.ma_crossover import (
    MACrossoverParams,
    MACrossoverStrategy,
)
from cadence.strategy_bots.ma_ribbon import MaRibbonParams, MaRibbonStrategy
from cadence.strategy_bots.macd_momentum import MacdMomentumParams, MacdMomentumStrategy
from cadence.strategy_bots.price_velocity_reversal import (
    PriceVelocityReversalParams,
    PriceVelocityReversalStrategy,
)
from cadence.strategy_bots.rolling_average_reversion import (
    RollingAverageReversionParams,
    RollingAverageReversionStrategy,
)
from cadence.strategy_bots.rsi_mean_reversion import (
    RsiMeanReversionParams,
    RsiMeanReversionStrategy,
)
from cadence.strategy_bots.strategy import Strategy, StrategyParams
from cadence.strategy_bots.trend_confirmation import (
    TrendConfirmationParams,
    TrendConfirmationStrategy,
)
from cadence.strategy_bots.vama import VamaParams, VamaStrategy
from cadence.strategy_bots.volume_breakout import (
    VolumeBreakoutParams,
    VolumeBreakoutStrategy,
)


@dataclass(frozen=True)
class StrategyRegistration:
    """A registered strategy: its implementation and parameter contract."""

    key: StrategyKey
    display_name: str
    explanation: str
    strategy: Strategy
    params_schema: type[StrategyParams]

    def parse_params(self, raw: Mapping[str, Any]) -> StrategyParams:
        """Validate ``raw`` against the schema, raising a domain error on failure."""
        try:
            return self.params_schema.model_validate(dict(raw))
        except ValidationError as exc:
            raise InvalidStrategyParamsError(str(exc)) from exc

    def required_history(self, raw: Mapping[str, Any]) -> int:
        """Number of bars this strategy needs for the given (raw) parameters."""
        return self.parse_params(raw).required_history


_REGISTRY: dict[StrategyKey, StrategyRegistration] = {
    StrategyKey.MA_CROSSOVER: StrategyRegistration(
        key=StrategyKey.MA_CROSSOVER,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.MA_CROSSOVER],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.MA_CROSSOVER],
        strategy=MACrossoverStrategy(),
        params_schema=MACrossoverParams,
    ),
    StrategyKey.RSI_MEAN_REVERSION: StrategyRegistration(
        key=StrategyKey.RSI_MEAN_REVERSION,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.RSI_MEAN_REVERSION],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.RSI_MEAN_REVERSION],
        strategy=RsiMeanReversionStrategy(),
        params_schema=RsiMeanReversionParams,
    ),
    StrategyKey.DONCHIAN_BREAKOUT: StrategyRegistration(
        key=StrategyKey.DONCHIAN_BREAKOUT,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.DONCHIAN_BREAKOUT],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.DONCHIAN_BREAKOUT],
        strategy=DonchianBreakoutStrategy(),
        params_schema=DonchianBreakoutParams,
    ),
    StrategyKey.ROLLING_AVERAGE_REVERSION: StrategyRegistration(
        key=StrategyKey.ROLLING_AVERAGE_REVERSION,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.ROLLING_AVERAGE_REVERSION],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.ROLLING_AVERAGE_REVERSION],
        strategy=RollingAverageReversionStrategy(),
        params_schema=RollingAverageReversionParams,
    ),
    StrategyKey.ATR_BAND_TREND: StrategyRegistration(
        key=StrategyKey.ATR_BAND_TREND,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.ATR_BAND_TREND],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.ATR_BAND_TREND],
        strategy=AtrBandTrendStrategy(),
        params_schema=AtrBandTrendParams,
    ),
    StrategyKey.ADX_TREND: StrategyRegistration(
        key=StrategyKey.ADX_TREND,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.ADX_TREND],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.ADX_TREND],
        strategy=AdxTrendStrategy(),
        params_schema=AdxTrendParams,
    ),
    StrategyKey.MACD_MOMENTUM: StrategyRegistration(
        key=StrategyKey.MACD_MOMENTUM,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.MACD_MOMENTUM],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.MACD_MOMENTUM],
        strategy=MacdMomentumStrategy(),
        params_schema=MacdMomentumParams,
    ),
    StrategyKey.HEIKIN_ASHI_TREND: StrategyRegistration(
        key=StrategyKey.HEIKIN_ASHI_TREND,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.HEIKIN_ASHI_TREND],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.HEIKIN_ASHI_TREND],
        strategy=HeikinAshiTrendStrategy(),
        params_schema=HeikinAshiTrendParams,
    ),
    StrategyKey.HMA_TREND: StrategyRegistration(
        key=StrategyKey.HMA_TREND,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.HMA_TREND],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.HMA_TREND],
        strategy=HmaTrendStrategy(),
        params_schema=HmaTrendParams,
    ),
    StrategyKey.MA_RIBBON: StrategyRegistration(
        key=StrategyKey.MA_RIBBON,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.MA_RIBBON],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.MA_RIBBON],
        strategy=MaRibbonStrategy(),
        params_schema=MaRibbonParams,
    ),
    StrategyKey.VAMA: StrategyRegistration(
        key=StrategyKey.VAMA,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.VAMA],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.VAMA],
        strategy=VamaStrategy(),
        params_schema=VamaParams,
    ),
    StrategyKey.PRICE_VELOCITY_REVERSAL: StrategyRegistration(
        key=StrategyKey.PRICE_VELOCITY_REVERSAL,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.PRICE_VELOCITY_REVERSAL],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.PRICE_VELOCITY_REVERSAL],
        strategy=PriceVelocityReversalStrategy(),
        params_schema=PriceVelocityReversalParams,
    ),
    StrategyKey.TREND_CONFIRMATION: StrategyRegistration(
        key=StrategyKey.TREND_CONFIRMATION,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.TREND_CONFIRMATION],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.TREND_CONFIRMATION],
        strategy=TrendConfirmationStrategy(),
        params_schema=TrendConfirmationParams,
    ),
    StrategyKey.VOLUME_BREAKOUT: StrategyRegistration(
        key=StrategyKey.VOLUME_BREAKOUT,
        display_name=STRATEGY_DISPLAY_NAMES[StrategyKey.VOLUME_BREAKOUT],
        explanation=STRATEGY_EXPLANATIONS[StrategyKey.VOLUME_BREAKOUT],
        strategy=VolumeBreakoutStrategy(),
        params_schema=VolumeBreakoutParams,
    ),
}


def get_strategy(key: str) -> StrategyRegistration:
    """Resolve a registered strategy by key, or raise ``UnknownStrategyError``."""
    try:
        strategy_key = StrategyKey(key)
    except ValueError as exc:
        raise UnknownStrategyError(key) from exc
    return _REGISTRY[strategy_key]


def list_strategies() -> list[StrategyRegistration]:
    """Return every registered strategy (for the strategy-catalog read)."""
    return list(_REGISTRY.values())
