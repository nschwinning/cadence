"""Enums for the portfolios capability.

Values mirror trading-bot's ``PortfolioSource`` and ``RiskProfile`` exactly so a
straight data migration stays possible.
"""

from __future__ import annotations

from enum import StrEnum


class PortfolioSource(StrEnum):
    """How a portfolio came to exist.

    ``LEGACY_*`` sources predate the current flows and are excluded from the
    default listing; ``AI_MANAGED`` portfolios are driven by the AI rebalancer.
    """

    RECOMMENDED = "recommended"
    MANUAL = "manual"
    LEGACY_BACKTEST = "legacy_backtest"
    LEGACY_CYCLE = "legacy_cycle"
    AI_MANAGED = "ai_managed"


class RiskProfile(StrEnum):
    """Coarse risk appetite associated with a portfolio."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


#: Sources considered "legacy" and hidden from the default portfolio listing.
LEGACY_SOURCES = frozenset({PortfolioSource.LEGACY_BACKTEST, PortfolioSource.LEGACY_CYCLE})
