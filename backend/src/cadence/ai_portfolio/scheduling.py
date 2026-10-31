"""Per-session rebalance-cadence due-check for the daily fan-out.

The daily rebalance cron fans out over every active session enrolled in a
rebalancing schedule mode (daily/weekly/monthly). Daily sessions are always due;
weekly and monthly sessions are due only once their calendar boundary — a new ISO
week or a new calendar month, evaluated in US/Eastern — has been crossed since
their last completed rebalance. A session that has never completed a rebalance is
due now, so its opening allocation is never delayed by its cadence.

The due-check is a pure function of (schedule mode, last-rebalanced timestamp,
now), kept here so it is trivially unit-testable in isolation from the router.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from cadence.paper_trading.constants import ScheduleMode

#: US/Eastern — cadence boundaries (ISO week / calendar month) are bucketed by the
#: Eastern calendar date, matching the timezone of the fixed rebalance cron slots.
MARKET_TIMEZONE = ZoneInfo("America/New_York")


def _as_aware(moment: datetime) -> datetime:
    """Return ``moment`` tz-aware, assuming UTC when it is naive."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def rebalance_due(
    schedule_mode: str,
    last_rebalanced_at: datetime | None,
    now: datetime,
    tz: ZoneInfo = MARKET_TIMEZONE,
) -> bool:
    """Return whether a session is due for a rebalance on this trigger run.

    - A **daily** session (and any non-weekly/monthly mode) is always due.
    - A session that has **never completed a rebalance** (``last_rebalanced_at`` is
      ``None``) is due now, regardless of cadence.
    - A **weekly** session is due once ``now`` falls in a different ISO week
      (year, week) than its last rebalance, in ``tz``.
    - A **monthly** session is due once ``now`` falls in a different calendar month
      (year, month) than its last rebalance, in ``tz``.

    Boundaries are bucketed by the Eastern calendar date, so a DST transition shifts
    only the wall-clock instant of the boundary, never which date a run falls on.
    """
    if schedule_mode not in (
        ScheduleMode.WEEKLY_REBALANCING.value,
        ScheduleMode.MONTHLY_REBALANCING.value,
    ):
        return True
    if last_rebalanced_at is None:
        return True

    last_date = _as_aware(last_rebalanced_at).astimezone(tz).date()
    today = _as_aware(now).astimezone(tz).date()

    if schedule_mode == ScheduleMode.WEEKLY_REBALANCING.value:
        last_iso = last_date.isocalendar()
        today_iso = today.isocalendar()
        return (today_iso.year, today_iso.week) != (last_iso.year, last_iso.week)
    # Monthly.
    return (today.year, today.month) != (last_date.year, last_date.month)
