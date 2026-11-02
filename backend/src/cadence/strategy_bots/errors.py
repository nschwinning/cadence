"""Domain errors for the strategy-bot subsystem.

These decouple the service/router from persistence details. The router maps each
to a distinct HTTP status code.
"""

from __future__ import annotations


class StrategyBotError(Exception):
    """Base class for all strategy-bot-domain errors."""


class BotSessionNotFoundError(StrategyBotError):
    """No bot session with the requested id exists."""


class UnknownStrategyError(StrategyBotError):
    """The requested strategy key is not registered."""


class InvalidStrategyParamsError(StrategyBotError):
    """The supplied strategy parameters failed the strategy's schema validation."""


class IneligibleAssetError(StrategyBotError):
    """The chosen asset is not an eligible, tradable equity in the universe.

    Bots are long-only equities-only in v1, so a non-eligible, non-equity, or
    unknown asset is rejected at creation and surfaced as 422 by the router.
    """


class BotSessionNotArchivableError(StrategyBotError):
    """The session cannot be archived because it is not stopped."""


class InvalidBotBenchmarkError(StrategyBotError):
    """The requested benchmark id is not in the fixed benchmark catalog."""
