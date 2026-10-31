"""Unit tests for the rebalance-cadence primitives.

Covers the pure pieces of ``add-rebalance-cadence-options``: the ``ScheduleMode``
members and the cadence <-> schedule-mode mapping, the ``AIBuildParams`` cadence
round-trip, and the calendar-boundary ``rebalance_due`` due-check (daily always
due, weekly across an ISO-week boundary, monthly across a calendar-month boundary,
never-allocated due now, ET boundary correctness).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cadence.ai_portfolio.params import AIBuildParams
from cadence.ai_portfolio.scheduling import MARKET_TIMEZONE, rebalance_due
from cadence.paper_trading.constants import (
    REBALANCING_SCHEDULE_MODES,
    RebalanceCadence,
    ScheduleMode,
    cadence_to_schedule_mode,
    schedule_mode_to_cadence,
)

# --------------------------------------------------------------------------- #
# 5.1 enum + mapping round-trips
# --------------------------------------------------------------------------- #


def test_schedule_mode_has_weekly_and_monthly() -> None:
    assert ScheduleMode.WEEKLY_REBALANCING.value == "WEEKLY_REBALANCING"
    assert ScheduleMode.MONTHLY_REBALANCING.value == "MONTHLY_REBALANCING"
    # Values survive the StrEnum round-trip.
    assert ScheduleMode("WEEKLY_REBALANCING") is ScheduleMode.WEEKLY_REBALANCING
    assert ScheduleMode("MONTHLY_REBALANCING") is ScheduleMode.MONTHLY_REBALANCING


@pytest.mark.parametrize(
    ("cadence", "mode"),
    [
        (RebalanceCadence.DAILY.value, ScheduleMode.DAILY_REBALANCING),
        (RebalanceCadence.WEEKLY.value, ScheduleMode.WEEKLY_REBALANCING),
        (RebalanceCadence.MONTHLY.value, ScheduleMode.MONTHLY_REBALANCING),
    ],
)
def test_cadence_to_schedule_mode(cadence: str, mode: ScheduleMode) -> None:
    assert cadence_to_schedule_mode(cadence) is mode
    # Inverse maps back to the originating cadence.
    assert schedule_mode_to_cadence(mode.value).value == cadence


def test_cadence_schedule_mode_round_trip_set() -> None:
    assert REBALANCING_SCHEDULE_MODES == {
        ScheduleMode.DAILY_REBALANCING.value,
        ScheduleMode.WEEKLY_REBALANCING.value,
        ScheduleMode.MONTHLY_REBALANCING.value,
    }


def test_unknown_cadence_and_mode_default_to_daily() -> None:
    assert cadence_to_schedule_mode("nonsense") is ScheduleMode.DAILY_REBALANCING
    # Legacy/non-rebalancing modes read as daily.
    assert schedule_mode_to_cadence(ScheduleMode.MANUAL.value) is RebalanceCadence.DAILY
    assert schedule_mode_to_cadence("whatever") is RebalanceCadence.DAILY


# --------------------------------------------------------------------------- #
# 5.1 AIBuildParams cadence round-trip
# --------------------------------------------------------------------------- #


def test_build_params_default_cadence_is_daily() -> None:
    assert AIBuildParams().rebalance_cadence == RebalanceCadence.DAILY.value


@pytest.mark.parametrize(
    "cadence",
    [
        RebalanceCadence.DAILY.value,
        RebalanceCadence.WEEKLY.value,
        RebalanceCadence.MONTHLY.value,
    ],
)
def test_build_params_cadence_round_trips(cadence: str) -> None:
    params = AIBuildParams(rebalance_cadence=cadence)
    payload = params.to_payload()
    assert payload["rebalance_cadence"] == cadence
    assert AIBuildParams.from_payload(payload).rebalance_cadence == cadence


def test_build_params_missing_cadence_defaults_to_daily() -> None:
    # A payload persisted before this field existed reconstructs as daily.
    assert (
        AIBuildParams.from_payload({"allocated_capital": 5000}).rebalance_cadence
        == RebalanceCadence.DAILY.value
    )


# --------------------------------------------------------------------------- #
# 5.2 rebalance_due calendar-boundary due-check
# --------------------------------------------------------------------------- #

_ET = MARKET_TIMEZONE


def _et(year: int, month: int, day: int, hour: int = 10) -> datetime:
    """A timezone-aware ET datetime at a weekday-cron-ish morning hour."""
    return datetime(year, month, day, hour, tzinfo=_ET)


def test_daily_always_due() -> None:
    # Even a daily session rebalanced moments ago is due again.
    now = _et(2026, 3, 10)
    assert rebalance_due(ScheduleMode.DAILY_REBALANCING.value, now, now) is True


def test_never_allocated_is_due_for_every_cadence() -> None:
    now = _et(2026, 3, 10)
    for mode in (
        ScheduleMode.DAILY_REBALANCING,
        ScheduleMode.WEEKLY_REBALANCING,
        ScheduleMode.MONTHLY_REBALANCING,
    ):
        assert rebalance_due(mode.value, None, now) is True


def test_weekly_due_only_across_iso_week_boundary() -> None:
    mode = ScheduleMode.WEEKLY_REBALANCING.value
    # Mon 2026-03-02 and Fri 2026-03-06 are the same ISO week -> not due.
    assert rebalance_due(mode, _et(2026, 3, 2), _et(2026, 3, 6)) is False
    # Mon 2026-03-09 is the next ISO week -> due.
    assert rebalance_due(mode, _et(2026, 3, 2), _et(2026, 3, 9)) is True


def test_weekly_boundary_spans_year_end() -> None:
    mode = ScheduleMode.WEEKLY_REBALANCING.value
    # Dec 29 2025 and Dec 31 2025 share ISO week 2026-W01 -> not due.
    assert rebalance_due(mode, _et(2025, 12, 29), _et(2025, 12, 31)) is False
    # Jan 5 2026 begins ISO week 2026-W02 -> due.
    assert rebalance_due(mode, _et(2025, 12, 29), _et(2026, 1, 5)) is True


def test_monthly_due_only_across_calendar_month_boundary() -> None:
    mode = ScheduleMode.MONTHLY_REBALANCING.value
    # Same calendar month -> not due.
    assert rebalance_due(mode, _et(2026, 3, 2), _et(2026, 3, 31)) is False
    # New calendar month -> due.
    assert rebalance_due(mode, _et(2026, 3, 31), _et(2026, 4, 1)) is True


def test_monthly_boundary_spans_year_end() -> None:
    mode = ScheduleMode.MONTHLY_REBALANCING.value
    assert rebalance_due(mode, _et(2025, 12, 1), _et(2025, 12, 31)) is False
    assert rebalance_due(mode, _et(2025, 12, 31), _et(2026, 1, 2)) is True


def test_monthly_weekend_month_start_fires_on_first_trading_day() -> None:
    # 2026-08-01 is a Saturday; the first weekday-cron run that month is Mon
    # 2026-08-03. A session last rebalanced in July is due on that first run.
    mode = ScheduleMode.MONTHLY_REBALANCING.value
    last = _et(2026, 7, 15)
    assert rebalance_due(mode, last, _et(2026, 8, 3)) is True


def test_boundaries_bucketed_in_eastern_time() -> None:
    # A UTC instant just after midnight UTC on the 1st is still the previous
    # month in ET, so a monthly session is NOT yet due at that instant.
    mode = ScheduleMode.MONTHLY_REBALANCING.value
    last = datetime(2026, 4, 15, 12, tzinfo=UTC)
    # 2026-05-01 00:30 UTC == 2026-04-30 20:30 ET -> still April in ET.
    just_after_utc_midnight = datetime(2026, 5, 1, 0, 30, tzinfo=UTC)
    assert rebalance_due(mode, last, just_after_utc_midnight) is False
    # 2026-05-01 12:00 UTC == 2026-05-01 08:00 ET -> now May in ET -> due.
    morning_et = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    assert rebalance_due(mode, last, morning_et) is True


def test_naive_last_rebalanced_at_treated_as_utc() -> None:
    # A naive timestamp must not raise; it is assumed UTC.
    mode = ScheduleMode.WEEKLY_REBALANCING.value
    last_naive = datetime(2026, 3, 2, 14, 0)  # noqa: DTZ001 - intentional naive input
    assert rebalance_due(mode, last_naive, _et(2026, 3, 9)) is True
