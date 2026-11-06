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

from cadence.strategy_bots.constants import (
    STRATEGY_DISPLAY_NAMES,
    STRATEGY_EXPLANATIONS,
    StrategyKey,
)
from cadence.strategy_bots.errors import (
    InvalidStrategyParamsError,
    UnknownStrategyError,
)
from cadence.strategy_bots.ma_crossover import (
    MACrossoverParams,
    MACrossoverStrategy,
)
from cadence.strategy_bots.rsi_mean_reversion import (
    RsiMeanReversionParams,
    RsiMeanReversionStrategy,
)
from cadence.strategy_bots.strategy import Strategy, StrategyParams


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
