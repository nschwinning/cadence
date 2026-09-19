"""Benchmark price ingestion and read-time comparison math.

The system owns a daily closing-price series per catalog benchmark
(:class:`~cadence.paper_trading.models.BenchmarkPrice`), filled by a scheduled
cron job (:func:`ingest_benchmark_prices`). A session's comparison is derived on
read from that series: load the session's benchmark closes into a
:class:`BenchmarkSeries`, resolve each date to the last stored close on or before
it, and rebase a buy-and-hold of the session's allocated capital to the session's
start date. Nothing derived is stored.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from cadence.paper_trading.constants import Benchmark, benchmark_symbol
from cadence.paper_trading.models import BenchmarkPrice

logger = logging.getLogger(__name__)

# PostgreSQL caps a single statement at 65,535 (2^16-1) bound parameters. Each
# upserted row binds 3 params (benchmark, price_date, close), so a full-history
# fetch (SP500's ``period="max"`` returns ~24,800 daily bars back to 1927 →
# ~74k params) overflows one INSERT. Chunk to stay well under the cap: 5,000
# rows * 3 = 15,000 params per statement.
_UPSERT_CHUNK_ROWS = 5_000


def ingest_benchmark_prices(
    session: Session, provider: object
) -> dict[str, int]:
    """Fetch and upsert the daily close series for every catalog benchmark.

    For each :class:`Benchmark`, calls ``provider.fetch_history(symbol)`` and
    upserts every returned daily bar into ``benchmark_prices`` (idempotent per
    ``(benchmark, price_date)``: a re-run updates the stored close rather than
    duplicating it). The full returned history is upserted, so the first run
    backfills enough history to compare sessions that started in the past. A
    benchmark whose fetch raises is logged and skipped without aborting the
    others. Returns a map of benchmark id to the number of rows upserted.

    ``provider`` is a :class:`~cadence.assets.market_data.MarketDataProvider`
    (typed loosely here to avoid importing the assets domain into this module).
    """
    counts: dict[str, int] = {}
    for benchmark in Benchmark:
        symbol = benchmark_symbol(benchmark)
        try:
            bars = provider.fetch_history(symbol)  # type: ignore[attr-defined]

            rows = [
                {
                    "benchmark": benchmark.value,
                    "price_date": bar.date,
                    "close": bar.close,
                }
                for bar in bars
            ]
            if not rows:
                counts[benchmark.value] = 0
                continue

            # Chunk the upsert so each INSERT stays under PostgreSQL's
            # 65,535-bound-parameter cap (see ``_UPSERT_CHUNK_ROWS``). All chunks
            # for a benchmark commit together so the benchmark is stored atomically.
            for start in range(0, len(rows), _UPSERT_CHUNK_ROWS):
                chunk = rows[start : start + _UPSERT_CHUNK_ROWS]
                stmt = pg_insert(BenchmarkPrice).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_benchmark_prices_benchmark_date",
                    set_={"close": stmt.excluded.close},
                )
                session.execute(stmt)
            session.commit()
            counts[benchmark.value] = len(rows)
        except Exception as exc:  # noqa: BLE001 - one benchmark can't abort the batch
            session.rollback()
            logger.warning(
                "benchmark ingestion: failed for %s (%s): %s",
                benchmark.value,
                symbol,
                exc,
            )
            counts[benchmark.value] = 0
            continue

    return counts


@dataclass(frozen=True)
class BenchmarkSeries:
    """A benchmark's stored daily closes, ready for date-aligned lookups.

    ``dates`` is ascending and index-aligned to ``closes``. :meth:`close_on_or_before`
    resolves any date to the last stored close on or before it (the date-alignment
    rule: benchmark closes exist only on trading days, but snapshot dates may fall on
    non-trading days), returning ``None`` when nothing is stored on or before it.
    """

    dates: list[date]
    closes: list[float]

    @property
    def empty(self) -> bool:
        return not self.dates

    def close_on_or_before(self, when: date) -> float | None:
        """Return the last stored close on or before ``when`` (``None`` if none)."""
        # ``bisect_right`` gives the insertion point after any equal date, so the
        # element before it is the last close on or before ``when``.
        idx = bisect.bisect_right(self.dates, when)
        if idx == 0:
            return None
        return self.closes[idx - 1]


def load_benchmark_series(session: Session, benchmark: str) -> BenchmarkSeries:
    """Load a benchmark's stored closes (ascending by date) into a series."""
    stmt = (
        select(BenchmarkPrice.price_date, BenchmarkPrice.close)
        .where(BenchmarkPrice.benchmark == benchmark)
        .order_by(BenchmarkPrice.price_date.asc())
    )
    rows = session.execute(stmt).all()
    dates = [row[0] for row in rows]
    closes = [row[1] for row in rows]
    return BenchmarkSeries(dates=dates, closes=closes)


def rebased_benchmark_value(
    series: BenchmarkSeries,
    *,
    allocated_capital: float,
    start_date: date,
    as_of: date,
) -> float | None:
    """Value a buy-and-hold of ``allocated_capital`` in the benchmark at ``as_of``.

    ``allocated_capital * close(as_of) / close(start_date)`` using the last stored
    close on or before each date (so the curve starts equal to allocated capital on
    the session's first snapshot date). Returns ``None`` when the series has no close
    on or before the start date or the as-of date, or the start close is non-positive
    — the read degrades gracefully rather than erroring.
    """
    start_close = series.close_on_or_before(start_date)
    if start_close is None or start_close <= 0:
        return None
    as_of_close = series.close_on_or_before(as_of)
    if as_of_close is None:
        return None
    return allocated_capital * as_of_close / start_close


def benchmark_return_fraction(
    series: BenchmarkSeries,
    *,
    start_date: date,
    as_of: date,
) -> float | None:
    """Fractional buy-and-hold return of the benchmark from ``start_date`` to ``as_of``.

    ``close(as_of) / close(start_date) - 1`` using the last stored close on or before
    each date. Returns ``None`` when either close is unavailable or the start close is
    non-positive.
    """
    start_close = series.close_on_or_before(start_date)
    if start_close is None or start_close <= 0:
        return None
    as_of_close = series.close_on_or_before(as_of)
    if as_of_close is None:
        return None
    return as_of_close / start_close - 1.0
