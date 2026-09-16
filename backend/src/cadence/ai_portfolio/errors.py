"""Domain errors for the AI-managed portfolio capability.

These decouple the service/router from persistence details. The router maps each
to a distinct HTTP status code.
"""

from __future__ import annotations


class AIPortfolioError(Exception):
    """Base class for all AI-portfolio-domain errors."""


class AIPortfolioValidationError(AIPortfolioError):
    """The requested build parameters are invalid (e.g. too few tickers)."""


class EventNotFoundError(AIPortfolioError):
    """No AI portfolio event with the requested id exists."""


class SessionNotEligibleError(AIPortfolioError):
    """The session cannot be rebalanced (not AI-managed, or not active)."""


class RebalancePromptNotFoundError(AIPortfolioError):
    """No rebalance prompt version exists in the database to run against."""
