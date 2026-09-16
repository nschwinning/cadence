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
