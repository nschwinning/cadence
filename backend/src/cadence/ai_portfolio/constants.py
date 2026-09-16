"""Enums and constants for the AI-managed portfolio capability.

An ``ai_portfolio_events`` row is the audit trail for one build or rebalance job.
``EventType``/``EventStatus`` values are stored as their string values (non-native
enums, like the rest of the codebase). The strategy key marks a paper-trading
session as AI-managed so the rebalance flows can find and validate it.
"""

from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Which AI job an :class:`~cadence.ai_portfolio.models.AIPortfolioEvent` records."""

    BUILD = "build"
    REBALANCE = "rebalance"
    CLOSE = "close"


class EventStatus(StrEnum):
    """Lifecycle status of an AI portfolio event.

    ``QUEUED`` → ``RUNNING`` → a terminal status. ``PARTIAL`` means the job ran but
    some per-ticker orders failed; ``SKIPPED`` means a rebalance was a no-op because
    the market was closed (no orders were placed).
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


#: Statuses from which no further progress is made.
TERMINAL_STATUSES = frozenset(
    {
        EventStatus.SUCCEEDED,
        EventStatus.PARTIAL,
        EventStatus.FAILED,
        EventStatus.SKIPPED,
    }
)

#: Strategy key identifying an AI-managed buy-and-hold paper-trading session.
AI_STRATEGY_KEY = "ai_buy_hold"
