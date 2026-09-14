"""Enums for the paper-trading capability.

``ScheduleMode`` values mirror trading-bot exactly (upper-cased). Trade side and
order status reuse the broker vocabulary (:mod:`cadence.broker.models`) so a
recorded paper trade lines up with the broker fills it came from.
"""

from __future__ import annotations

from enum import StrEnum


class ScheduleMode(StrEnum):
    """How a paper-trading session is run automatically.

    - ``MANUAL``: no automatic runs; only explicit user actions touch it.
    - ``SCHEDULED``: run by the periodic intraday signal-scan cron.
    - ``DAILY_REBALANCING``: rebalanced once per weekday morning by the AI
      rebalance cron (AI buy-and-hold portfolios opting into daily rebalancing).
    """

    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    DAILY_REBALANCING = "DAILY_REBALANCING"


class SessionStatus(StrEnum):
    """Lifecycle status of a paper-trading session."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class RunStatus(StrEnum):
    """Outcome of a single session run."""

    SUCCESS = "success"
    FAILURE = "failure"


#: Default trade side/status come from the broker vocabulary; imported here for
#: convenience so the paper-trading layer has a single enums module.
DEFAULT_ORDER_STATUS = "filled"
DEFAULT_RUN_TRIGGER = "scheduled"
