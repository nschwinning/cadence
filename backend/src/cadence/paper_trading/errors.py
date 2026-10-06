"""Domain errors for the paper-trading capability.

These decouple the service/router from persistence details. The router maps each
to a distinct HTTP status code.
"""

from __future__ import annotations


class PaperTradingError(Exception):
    """Base class for all paper-trading-domain errors."""


class SessionNotFoundError(PaperTradingError):
    """No paper-trading session with the requested id exists."""


class DuplicateSessionError(PaperTradingError):
    """A session already exists for this ``(portfolio_id, strategy_key)`` pair."""


class SessionNotArchivableError(PaperTradingError):
    """The session cannot be archived because it is not stopped."""


class InvalidBenchmarkError(PaperTradingError):
    """The requested benchmark id is not in the fixed benchmark catalog."""


class InvalidAssetScopeError(PaperTradingError):
    """The requested asset scope is not one of the supported ``AssetScope`` values.

    Carries the allowed scopes in its message so the router can surface them (422).
    """


class InvalidCapitalChangeError(PaperTradingError):
    """The requested capital change is not allowed (e.g. a non-positive amount).

    Capital increases are increase-only; an amount at or below zero is rejected
    and surfaced as 422 by the router.
    """
