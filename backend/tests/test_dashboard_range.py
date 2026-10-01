"""Unit tests for the dashboard range enum and its start-date resolver.

Pure date arithmetic (no DB): each supported range resolves to the expected
inclusive window start relative to a fixed "today", including the YTD (Jan 1) and
Max (unbounded → ``None``) special cases.
"""

from __future__ import annotations

from datetime import date

from cadence.dashboard.constants import DashboardRange, resolve_range_start

_TODAY = date(2026, 6, 15)


def test_fixed_length_ranges_resolve_to_day_offsets() -> None:
    assert resolve_range_start(DashboardRange.DAY, today=_TODAY) == date(2026, 6, 14)
    assert resolve_range_start(DashboardRange.WEEK, today=_TODAY) == date(2026, 6, 8)
    assert resolve_range_start(DashboardRange.MONTH, today=_TODAY) == date(2026, 5, 16)
    assert resolve_range_start(DashboardRange.YEAR, today=_TODAY) == date(2025, 6, 15)


def test_ytd_resolves_to_first_of_the_year() -> None:
    assert resolve_range_start(DashboardRange.YTD, today=_TODAY) == date(2026, 1, 1)


def test_max_resolves_to_none() -> None:
    assert resolve_range_start(DashboardRange.MAX, today=_TODAY) is None


def test_range_values_are_the_wire_strings() -> None:
    assert {r.value for r in DashboardRange} == {
        "1D",
        "1W",
        "1M",
        "YTD",
        "1Y",
        "Max",
    }
