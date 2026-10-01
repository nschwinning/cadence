"""Unit tests for stored price-history storage, ingestion, and range returns."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider

from cadence.assets.models import Asset
from cadence.dashboard.constants import DashboardRange
from cadence.price_history import service
from cadence.price_history.models import PriceHistory


def _asset(db_session: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    return asset


def _count(db_session: Session, asset_id: int) -> int:
    return db_session.execute(
        select(func.count())
        .select_from(PriceHistory)
        .where(PriceHistory.asset_id == asset_id)
    ).scalar_one()


# --- store_closes (upsert) --------------------------------------------------


def test_store_closes_upserts_same_date(db_session: Session) -> None:
    asset = _asset(db_session, "AAA")

    service.store_closes(db_session, asset.id, [(date(2024, 1, 2), 100.0)])
    service.store_closes(db_session, asset.id, [(date(2024, 1, 2), 125.0)])

    assert _count(db_session, asset.id) == 1
    stored = db_session.execute(
        select(PriceHistory.close).where(PriceHistory.asset_id == asset.id)
    ).scalar_one()
    assert stored == 125.0


def test_store_closes_dedupes_within_batch(db_session: Session) -> None:
    asset = _asset(db_session, "BBB")

    written = service.store_closes(
        db_session,
        asset.id,
        [(date(2024, 1, 2), 10.0), (date(2024, 1, 2), 20.0)],
    )

    assert written == 1
    assert _count(db_session, asset.id) == 1


# --- asset_return over a range ----------------------------------------------


def test_asset_return_fixed_range(db_session: Session) -> None:
    asset = _asset(db_session, "FIX")
    service.store_closes(
        db_session,
        asset.id,
        [
            (date(2024, 4, 1), 100.0),  # before the 1M window start -> excluded
            (date(2024, 5, 10), 110.0),  # first close in window
            (date(2024, 6, 1), 121.0),  # latest
        ],
    )

    result = service.asset_return(
        db_session,
        asset_id=asset.id,
        range_=DashboardRange.MONTH,
        today=date(2024, 6, 1),
    )

    assert result is not None
    assert round(result, 6) == round(121.0 / 110.0 - 1.0, 6)


def test_asset_return_ytd(db_session: Session) -> None:
    asset = _asset(db_session, "YTD")
    service.store_closes(
        db_session,
        asset.id,
        [
            (date(2023, 12, 15), 90.0),  # prior year -> excluded
            (date(2024, 1, 5), 100.0),  # first close of the year
            (date(2024, 6, 1), 120.0),
        ],
    )

    result = service.asset_return(
        db_session,
        asset_id=asset.id,
        range_=DashboardRange.YTD,
        today=date(2024, 6, 1),
    )

    assert result is not None
    assert round(result, 6) == 0.2


def test_asset_return_max_uses_earliest(db_session: Session) -> None:
    asset = _asset(db_session, "MAX")
    service.store_closes(
        db_session,
        asset.id,
        [
            (date(2020, 1, 1), 50.0),
            (date(2022, 1, 1), 75.0),
            (date(2024, 6, 1), 100.0),
        ],
    )

    result = service.asset_return(
        db_session,
        asset_id=asset.id,
        range_=DashboardRange.MAX,
        today=date(2024, 6, 1),
    )

    assert result == 1.0


def test_asset_return_insufficient_history_is_none(db_session: Session) -> None:
    asset = _asset(db_session, "THIN")
    service.store_closes(db_session, asset.id, [(date(2024, 6, 1), 100.0)])

    # Single close -> cannot resolve a start/end pair for the range.
    assert (
        service.asset_return(
            db_session,
            asset_id=asset.id,
            range_=DashboardRange.MONTH,
            today=date(2024, 6, 1),
        )
        is None
    )

    # Closes exist but all predate the fixed window -> no start resolves.
    other = _asset(db_session, "STALE")
    service.store_closes(
        db_session,
        other.id,
        [(date(2023, 1, 1), 10.0), (date(2023, 2, 1), 11.0)],
    )
    assert (
        service.asset_return(
            db_session,
            asset_id=other.id,
            range_=DashboardRange.MONTH,
            today=date(2024, 6, 1),
        )
        is None
    )


# --- provider batch method --------------------------------------------------


def test_fake_provider_synthetic_closes_are_deterministic() -> None:
    provider = FakeMarketDataProvider(synthetic_closes=True)
    start, end = date(2024, 1, 1), date(2024, 1, 10)

    first = provider.fetch_daily_closes(["AAA", "BBB"], start, end)
    second = provider.fetch_daily_closes(["AAA", "BBB"], start, end)

    assert set(first) == {"AAA", "BBB"}
    # Ascending by date and stable across calls.
    assert first["AAA"] == sorted(first["AAA"])
    assert first == second
    # Per-ticker series differ.
    assert first["AAA"] != first["BBB"]


# --- ingestion --------------------------------------------------------------


def test_ingest_latest_skips_absent_asset_and_stores_others(
    db_session: Session,
) -> None:
    good_a = _asset(db_session, "GOODA")
    missing = _asset(db_session, "GONE")
    good_c = _asset(db_session, "GOODC")
    day = date(2024, 6, 3)
    provider = FakeMarketDataProvider(
        daily_closes_by_ticker={
            "GOODA": [(day, 10.0)],
            "GOODC": [(day, 30.0)],
        }  # "GONE" is intentionally absent from the provider response
    )

    stored = service.ingest_latest(
        db_session, provider, [good_a, missing, good_c], today=date(2024, 6, 3)
    )

    assert stored == 2
    assert _count(db_session, good_a.id) == 1
    assert _count(db_session, good_c.id) == 1
    assert _count(db_session, missing.id) == 0


def test_ingest_latest_is_idempotent(db_session: Session) -> None:
    asset = _asset(db_session, "IDEM")
    day = date(2024, 6, 3)
    provider = FakeMarketDataProvider(
        daily_closes_by_ticker={"IDEM": [(day, 42.0)]}
    )

    service.ingest_latest(db_session, provider, [asset], today=day)
    service.ingest_latest(db_session, provider, [asset], today=day)

    assert _count(db_session, asset.id) == 1


def test_backfill_stores_history(db_session: Session) -> None:
    asset = _asset(db_session, "BACK")
    provider = FakeMarketDataProvider(
        daily_closes_by_ticker={
            "BACK": [(date(2021, 6, 1), 10.0), (date(2021, 6, 2), 11.0)]
        }
    )

    written = service.backfill(
        db_session, provider, asset, today=date(2024, 6, 1)
    )

    assert written == 2
    assert _count(db_session, asset.id) == 2


def test_backfill_provider_failure_returns_zero(db_session: Session) -> None:
    asset = _asset(db_session, "FAIL")
    provider = FakeMarketDataProvider(daily_closes_error=RuntimeError("boom"))

    written = service.backfill(db_session, provider, asset)

    assert written == 0
    assert _count(db_session, asset.id) == 0
