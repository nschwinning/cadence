"""Storage and per-asset range returns for stored daily close prices.

``store_closes`` upserts a batch of ``(date, close)`` points for one asset
(unique on ``(asset_id, date)``, last write wins). ``backfill`` /
``ingest_latest`` fetch closes from the market-data provider and persist them
best-effort (per-asset failures are logged and skipped). ``asset_return``
computes an asset's close-to-close market return over a ``DashboardRange`` from
its own stored dates, or ``None`` when the asset lacks enough history to resolve
a start point for the range.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from cadence.assets.market_data import MarketDataProvider
from cadence.assets.models import Asset
from cadence.config import settings
from cadence.dashboard.constants import DashboardRange, resolve_range_start
from cadence.price_history.constants import DAILY_INGEST_LOOKBACK_DAYS
from cadence.price_history.models import PriceHistory

logger = logging.getLogger(__name__)


def store_closes(
    session: Session, asset_id: int, closes: Iterable[tuple[date, float]]
) -> int:
    """Upsert daily closes for one asset; re-ingesting a date overwrites it.

    Duplicate dates within ``closes`` are collapsed (last value wins) before the
    insert so a single statement never conflicts with itself. Returns the number
    of distinct dates written. Does not commit — the caller controls the
    transaction boundary.
    """

    deduped: dict[date, float] = {}
    for day, close in closes:
        if close is None:
            continue
        deduped[day] = float(close)
    if not deduped:
        return 0
    rows = [
        {"asset_id": asset_id, "date": day, "close": close}
        for day, close in deduped.items()
    ]
    stmt = pg_insert(PriceHistory).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_history_asset_date",
        set_={"close": stmt.excluded.close},
    )
    session.execute(stmt)
    return len(rows)


def backfill(
    session: Session,
    provider: MarketDataProvider,
    asset: Asset,
    *,
    lookback_years: int | None = None,
    today: date | None = None,
) -> int:
    """Backfill one asset's daily closes over a bounded lookback window.

    Best-effort: a provider failure (or no usable history) leaves the asset with
    no stored history and returns 0 rather than raising, so an asset add never
    fails because of price history.
    """

    lookback_years = lookback_years or settings.PRICE_HISTORY_BACKFILL_YEARS
    today = today or datetime.now(tz=UTC).date()
    start = today - timedelta(days=365 * lookback_years)
    try:
        by_ticker = provider.fetch_daily_closes([asset.ticker], start, today)
    except Exception:
        logger.warning(
            "price-history backfill fetch failed for %s", asset.ticker, exc_info=True
        )
        return 0
    closes = by_ticker.get(asset.ticker) or []
    if not closes:
        return 0
    try:
        written = store_closes(session, asset.id, closes)
        session.commit()
        return written
    except Exception:
        session.rollback()
        logger.warning(
            "price-history backfill store failed for %s", asset.ticker, exc_info=True
        )
        return 0


def ingest_latest(
    session: Session,
    provider: MarketDataProvider,
    assets: list[Asset],
    *,
    lookback_days: int = DAILY_INGEST_LOOKBACK_DAYS,
    today: date | None = None,
) -> int:
    """Append the latest daily closes for all tracked assets (idempotent).

    Fetches the window in one batch call, then stores per asset so a single
    asset's absence from the provider response (or a store error) is logged and
    skipped while the remaining assets are still ingested. Returns the total
    number of dates written across all assets.
    """

    if not assets:
        return 0
    today = today or datetime.now(tz=UTC).date()
    start = today - timedelta(days=lookback_days)
    tickers = [asset.ticker for asset in assets]
    try:
        by_ticker = provider.fetch_daily_closes(tickers, start, today)
    except Exception:
        logger.warning("price-history daily ingestion fetch failed", exc_info=True)
        return 0
    stored = 0
    for asset in assets:
        closes = by_ticker.get(asset.ticker)
        if not closes:
            continue
        try:
            stored += store_closes(session, asset.id, closes)
            session.commit()
        except Exception:
            session.rollback()
            logger.warning(
                "price-history ingestion store failed for %s",
                asset.ticker,
                exc_info=True,
            )
    return stored


def asset_return(
    session: Session,
    *,
    asset_id: int,
    range_: DashboardRange,
    today: date | None = None,
) -> float | None:
    """Close-to-close market return for an asset over a range (dividends excluded).

    The range start is resolved against the asset's own stored dates: the
    earliest close on/after the range start for a fixed range, the first close of
    the current calendar year for YTD, and the earliest stored close for Max.
    Returns ``None`` when fewer than two closes resolve for the range (not enough
    history to produce a meaningful return) rather than a misleading value.
    """

    today = today or datetime.now(tz=UTC).date()
    start = resolve_range_start(range_, today=today)
    stmt = select(PriceHistory.close).where(PriceHistory.asset_id == asset_id)
    if start is not None:
        stmt = stmt.where(PriceHistory.date >= start)
    stmt = stmt.order_by(PriceHistory.date)
    closes = list(session.execute(stmt).scalars().all())
    if len(closes) < 2:
        return None
    first, last = closes[0], closes[-1]
    if first == 0:
        return None
    return last / first - 1.0
