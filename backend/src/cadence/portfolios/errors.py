"""Domain errors for the portfolios capability.

These decouple the service/router from persistence details. The router maps each
to a distinct HTTP status code.
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base class for all portfolio-domain errors."""


class PortfolioValidationError(PortfolioError):
    """The requested portfolio parameters are invalid (e.g. no valid tickers)."""


class PortfolioNotFoundError(PortfolioError):
    """No portfolio with the requested id exists."""


class PortfolioNotArchivableError(PortfolioError):
    """The portfolio cannot be archived while it has an active or paused session."""
