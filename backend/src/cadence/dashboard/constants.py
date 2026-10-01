"""Shared constants for the dashboard overview.

Kept dependency-free (no service imports) so both ``dashboard.service`` and
``price_history.service`` can import the range enum and its start-date resolver
without forming an import cycle.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

# Recent-activity feed cap and performer list size for the overview.
RECENT_ACTIVITY_LIMIT = 15
PERFORMERS_LIMIT = 5

# Fixed daily rebalance cron slots (US/Eastern) used to approximate the next
# scheduled run in the automation summary. Matches the deployed cron schedule
# (09:35 and 16:15 ET); holidays are ignored (the approximation is flagged).
REBALANCE_CRON_SLOTS_ET = ((9, 35), (16, 15))


class DashboardRange(str, Enum):
    """Supported time horizons for the range-scoped dashboard overview."""

    DAY = "1D"
    WEEK = "1W"
    MONTH = "1M"
    YTD = "YTD"
    YEAR = "1Y"
    MAX = "Max"


# Fixed-length ranges expressed as a day offset from "today".
_RANGE_DAYS = {
    DashboardRange.DAY: 1,
    DashboardRange.WEEK: 7,
    DashboardRange.MONTH: 30,
    DashboardRange.YEAR: 365,
}


def resolve_range_start(range_: DashboardRange, *, today: date) -> date | None:
    """Resolve a range to its inclusive start date.

    Returns ``None`` for ``Max`` (meaning "from the earliest available point"),
    the first of the current calendar year for ``YTD``, and ``today`` minus the
    fixed offset for the length-based ranges.
    """

    if range_ is DashboardRange.MAX:
        return None
    if range_ is DashboardRange.YTD:
        return date(today.year, 1, 1)
    return today - timedelta(days=_RANGE_DAYS[range_])
