"""Tests for the benchmark catalog, price ingestion, and comparison math."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider

from cadence.assets.market_data import HistoryBar
from cadence.paper_trading.benchmark import (
    BenchmarkSeries,
    benchmark_return_fraction,
    ingest_benchmark_prices,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.paper_trading.constants import (
    BENCHMARK_DISPLAY_NAMES,
    BENCHMARK_SYMBOLS,
    Benchmark,
    benchmark_symbol,
)
from cadence.paper_trading.models import BenchmarkPrice

# --------------------------------------------------------------------------- #
# 1.1 Catalog
# --------------------------------------------------------------------------- #


def test_every_benchmark_has_name_and_symbol() -> None:
    for member in Benchmark:
        assert BENCHMARK_DISPLAY_NAMES[member]
        assert BENCHMARK_SYMBOLS[member]
    # The catalog maps exactly the enum members, nothing extra or missing.
    assert set(BENCHMARK_DISPLAY_NAMES) == set(Benchmark)
    assert set(BENCHMARK_SYMBOLS) == set(Benchmark)


def test_sp500_maps_to_gspc() -> None:
    assert benchmark_symbol(Benchmark.SP500) == "^GSPC"


# --------------------------------------------------------------------------- #
# 4.1 BenchmarkSeries.close_on_or_before
# --------------------------------------------------------------------------- #


def _series() -> BenchmarkSeries:
    return BenchmarkSeries(
        dates=[date(2026, 1, 3), date(2026, 1, 6)],
        closes=[100.0, 106.0],
    )


def test_close_on_or_before_exact_date() -> None:
    assert _series().close_on_or_before(date(2026, 1, 6)) == 106.0


def test_close_on_or_before_prior_trading_day() -> None:
    # Jan 5 is not stored -> resolves to the last close on or before it (Jan 3).
    assert _series().close_on_or_before(date(2026, 1, 5)) == 100.0


def test_close_on_or_before_pre_series_is_none() -> None:
    assert _series().close_on_or_before(date(2026, 1, 1)) is None
    assert BenchmarkSeries(dates=[], closes=[]).empty is True


# --------------------------------------------------------------------------- #
# 4.2 rebased_benchmark_value
# --------------------------------------------------------------------------- #


def test_rebased_value_first_snapshot_equals_allocated() -> None:
    series = _series()
    start = date(2026, 1, 3)
    # Valued at the start date the buy-and-hold equals the allocated capital.
    assert rebased_benchmark_value(
        series, allocated_capital=100_000.0, start_date=start, as_of=start
    ) == 100_000.0
    # +6% by Jan 6.
    assert rebased_benchmark_value(
        series, allocated_capital=100_000.0, start_date=start, as_of=date(2026, 1, 6)
    ) == 106_000.0


def test_rebased_value_null_when_no_prices() -> None:
    empty = BenchmarkSeries(dates=[], closes=[])
    assert (
        rebased_benchmark_value(
            empty,
            allocated_capital=100_000.0,
            start_date=date(2026, 1, 3),
            as_of=date(2026, 1, 6),
        )
        is None
    )


def test_benchmark_return_fraction_matches_price_move() -> None:
    series = _series()
    assert benchmark_return_fraction(
        series, start_date=date(2026, 1, 3), as_of=date(2026, 1, 6)
    ) == pytest.approx(0.06)
    # No close on or before the start -> null.
    assert (
        benchmark_return_fraction(
            series, start_date=date(2026, 1, 1), as_of=date(2026, 1, 6)
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 3.1 Ingestion (idempotent, one failure does not abort the batch)
# --------------------------------------------------------------------------- #


def _bars() -> list[HistoryBar]:
    return [
        HistoryBar(date=date(2026, 1, 3), close=100.0, volume=1_000.0),
        HistoryBar(date=date(2026, 1, 6), close=106.0, volume=1_000.0),
    ]


def _row_count(db_session: Session) -> int:
    return db_session.execute(
        select(func.count()).select_from(BenchmarkPrice)
    ).scalar_one()


def test_ingest_upserts_all_benchmarks(db_session: Session) -> None:
    provider = FakeMarketDataProvider(history=_bars())
    counts = ingest_benchmark_prices(db_session, provider)
    # Every catalog benchmark got its two bars stored.
    assert set(counts) == {b.value for b in Benchmark}
    assert all(c == 2 for c in counts.values())
    assert _row_count(db_session) == 2 * len(Benchmark)


def test_ingest_is_idempotent_on_rerun(db_session: Session) -> None:
    provider = FakeMarketDataProvider(history=_bars())
    ingest_benchmark_prices(db_session, provider)
    ingest_benchmark_prices(db_session, provider)
    # A re-run updates the same (benchmark, date) rows rather than duplicating.
    assert _row_count(db_session) == 2 * len(Benchmark)
    series = load_benchmark_series(db_session, Benchmark.SP500.value)
    assert series.dates == [date(2026, 1, 3), date(2026, 1, 6)]
    assert series.closes == [100.0, 106.0]


def test_ingest_one_failing_benchmark_does_not_abort_others(
    db_session: Session,
) -> None:
    failing = benchmark_symbol(Benchmark.DJIA)
    provider = FakeMarketDataProvider(
        history=_bars(),
        history_error_by_ticker={failing: RuntimeError("boom")},
    )
    counts = ingest_benchmark_prices(db_session, provider)
    # The failing benchmark is skipped (count 0); every other still upserts.
    assert counts[Benchmark.DJIA.value] == 0
    assert load_benchmark_series(db_session, Benchmark.DJIA.value).empty
    others = [c for b, c in counts.items() if b != Benchmark.DJIA.value]
    assert all(c == 2 for c in others)
    assert _row_count(db_session) == 2 * (len(Benchmark) - 1)
