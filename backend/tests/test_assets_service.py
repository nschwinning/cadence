"""Integration tests for the assets service against Postgres (fake provider)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider

from cadence.assets import service
from cadence.assets.category import AssetCategory
from cadence.assets.errors import (
    AssetNotFoundError,
    DuplicateAssetError,
    MarketDataUnavailableError,
    UnknownTickerError,
)
from cadence.assets.market_data import AssetDetailData, AssetInfo, HistoryBar
from cadence.assets.models import Asset, AssetDailySnapshot


def _detail_provider(
    current_price: float = 191.0,
    previous_close: float = 188.0,
) -> FakeMarketDataProvider:
    provider = _eligible_provider()
    provider._detail = AssetDetailData(
        current_price=current_price,
        previous_close=previous_close,
        short_description="A canned description.",
        price_history=[
            HistoryBar(date=date(2024, 1, 2), close=180.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 3), close=185.0, volume=1_100_000.0),
        ],
    )
    return provider


def _count_snapshots(db_session: Session, asset_id: int) -> int:
    return len(
        [
            row
            for row in db_session.query(AssetDailySnapshot).all()
            if row.asset_id == asset_id
        ]
    )


def _eligible_provider(
    quote_type: str = "EQUITY",
    company_name: str = "Test Co",
    sector_key: str | None = None,
    *,
    country: str | None = None,
    city: str | None = None,
    employees: int | None = None,
    website: str | None = None,
) -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name=company_name,
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type=quote_type,
            sector_key=sector_key,
            country=country,
            city=city,
            employees=employees,
            website=website,
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def test_add_asset_success_persists_and_normalizes(db_session: Session) -> None:
    asset = service.add_asset(db_session, "  tsco ", _eligible_provider())

    assert asset.id is not None
    assert asset.ticker == "TSCO"
    assert asset.name == "Test Co"
    assert asset.category == AssetCategory.STOCK.value
    assert asset.is_eligible is True
    assert asset.created_at is not None
    assert {c["name"] for c in asset.criteria_results} == {
        "price",
        "avg_daily_turnover",
        "market_cap",
        "history",
    }

    assert [a.ticker for a in service.list_assets(db_session)] == ["TSCO"]


def test_add_asset_persists_company_profile_fields(db_session: Session) -> None:
    asset = service.add_asset(
        db_session,
        "AAPL",
        _eligible_provider(
            country="United States",
            city="Cupertino",
            employees=164_000,
            website="https://apple.com",
        ),
    )

    assert asset.country == "United States"
    assert asset.city == "Cupertino"
    assert asset.employees == 164_000
    assert asset.website == "https://apple.com"


def test_add_asset_missing_company_profile_fields_stored_as_none(
    db_session: Session,
) -> None:
    # Provider omits the profile fields -> stored as NULL, add still succeeds.
    asset = service.add_asset(db_session, "NOCO", _eligible_provider())

    assert asset.country is None
    assert asset.city is None
    assert asset.employees is None
    assert asset.website is None


def test_add_asset_classifies_crypto(db_session: Session) -> None:
    asset = service.add_asset(
        db_session, "BTC-USD", _eligible_provider(quote_type="CRYPTOCURRENCY")
    )

    assert asset.category == AssetCategory.CRYPTO.value


def test_add_asset_persists_sector_for_equity(db_session: Session) -> None:
    asset = service.add_asset(
        db_session,
        "BANK",
        _eligible_provider(sector_key="financial-services"),
    )

    assert asset.sector == "financial-services"


def test_add_asset_sector_null_when_provider_reports_none(
    db_session: Session,
) -> None:
    # Non-equity/unknown: provider gives no sector -> stored as NULL.
    asset = service.add_asset(
        db_session,
        "BTC-USD",
        _eligible_provider(quote_type="CRYPTOCURRENCY", sector_key=None),
    )

    assert asset.sector is None


def test_add_asset_duplicate_raises(db_session: Session) -> None:
    service.add_asset(db_session, "DUP", _eligible_provider())

    with pytest.raises(DuplicateAssetError):
        service.add_asset(db_session, "dup", _eligible_provider())


def test_add_asset_unknown_ticker_raises_and_no_persist(
    db_session: Session,
) -> None:
    provider = FakeMarketDataProvider(info_error=UnknownTickerError("no data"))

    with pytest.raises(UnknownTickerError):
        service.add_asset(db_session, "NOPE", provider)

    assert service.list_assets(db_session) == []


def test_add_asset_provider_failure_no_partial_persist(
    db_session: Session,
) -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Flaky",
            exchange="NYSE",
            currency="USD",
            price=10.0,
            market_cap=2_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=[HistoryBar(date=date(2010, 1, 1), close=10.0, volume=100_000.0)],
        fx_error=MarketDataUnavailableError("fx down"),
    )

    with pytest.raises(MarketDataUnavailableError):
        service.add_asset(db_session, "FLKY", provider)

    assert service.list_assets(db_session) == []


def test_list_assets_pagination_and_default_order(db_session: Session) -> None:
    # Insert out of order to prove the default sort is ticker asc, not insert order.
    for ticker in ("CCC", "AAA", "DDD", "BBB"):
        service.add_asset(db_session, ticker, _eligible_provider())

    # Default order is ticker ascending, bounded page.
    page1 = service.list_assets(db_session, limit=2, offset=0)
    assert [a.ticker for a in page1] == ["AAA", "BBB"]

    page2 = service.list_assets(db_session, limit=2, offset=2)
    assert [a.ticker for a in page2] == ["CCC", "DDD"]

    # limit=None returns everything (back-compat with existing callers).
    assert len(service.list_assets(db_session)) == 4


def test_list_assets_sort_ticker_direction(db_session: Session) -> None:
    for ticker in ("BBB", "AAA", "CCC"):
        service.add_asset(db_session, ticker, _eligible_provider())

    asc = service.list_assets(db_session, sort="ticker", direction="asc")
    assert [a.ticker for a in asc] == ["AAA", "BBB", "CCC"]

    desc = service.list_assets(db_session, sort="ticker", direction="desc")
    assert [a.ticker for a in desc] == ["CCC", "BBB", "AAA"]


def test_list_assets_sort_by_name(db_session: Session) -> None:
    service.add_asset(db_session, "AAA", _eligible_provider(company_name="Charlie"))
    service.add_asset(db_session, "BBB", _eligible_provider(company_name="Alpha"))
    service.add_asset(db_session, "CCC", _eligible_provider(company_name="Bravo"))

    asc = service.list_assets(db_session, sort="name", direction="asc")
    assert [a.name for a in asc] == ["Alpha", "Bravo", "Charlie"]

    desc = service.list_assets(db_session, sort="name", direction="desc")
    assert [a.name for a in desc] == ["Charlie", "Bravo", "Alpha"]


def test_list_assets_sort_by_name_puts_nulls_last(db_session: Session) -> None:
    service.add_asset(db_session, "AAA", _eligible_provider(company_name="Alpha"))
    service.add_asset(db_session, "BBB", _eligible_provider(company_name="Bravo"))
    # An asset with no instrument name must sort last regardless of direction.
    db_session.add(
        Asset(
            ticker="ZZZ",
            name=None,
            category=AssetCategory.STOCK.value,
            currency="EUR",
            is_eligible=True,
            criteria_results=[],
        )
    )
    db_session.commit()

    asc = service.list_assets(db_session, sort="name", direction="asc")
    assert [a.ticker for a in asc] == ["AAA", "BBB", "ZZZ"]

    desc = service.list_assets(db_session, sort="name", direction="desc")
    assert [a.ticker for a in desc] == ["BBB", "AAA", "ZZZ"]


def test_list_assets_filter_by_category(db_session: Session) -> None:
    service.add_asset(db_session, "STK", _eligible_provider(quote_type="EQUITY"))
    service.add_asset(
        db_session, "BTC", _eligible_provider(quote_type="CRYPTOCURRENCY")
    )
    service.add_asset(db_session, "ETFX", _eligible_provider(quote_type="ETF"))

    only_stock = service.list_assets(db_session, categories=["stock"])
    assert [a.ticker for a in only_stock] == ["STK"]

    stock_or_etf = service.list_assets(db_session, categories=["stock", "etf"])
    assert sorted(a.ticker for a in stock_or_etf) == ["ETFX", "STK"]

    # Empty/None categories means all.
    assert len(service.list_assets(db_session, categories=[])) == 3
    assert len(service.list_assets(db_session, categories=None)) == 3


def test_list_assets_filter_by_sector(db_session: Session) -> None:
    service.add_asset(
        db_session, "BANK", _eligible_provider(sector_key="financial-services")
    )
    service.add_asset(
        db_session, "CHIP", _eligible_provider(sector_key="technology")
    )
    service.add_asset(
        db_session, "DRUG", _eligible_provider(sector_key="healthcare")
    )
    # Null-sector asset must never match a positive sector filter.
    service.add_asset(
        db_session, "COIN", _eligible_provider(quote_type="CRYPTOCURRENCY")
    )

    only_fin = service.list_assets(
        db_session, sectors=["financial-services"]
    )
    assert [a.ticker for a in only_fin] == ["BANK"]

    fin_or_tech = service.list_assets(
        db_session, sectors=["financial-services", "technology"]
    )
    assert sorted(a.ticker for a in fin_or_tech) == ["BANK", "CHIP"]

    # Empty/None sectors means all (including the null-sector row).
    assert len(service.list_assets(db_session, sectors=[])) == 4
    assert len(service.list_assets(db_session, sectors=None)) == 4
    # A positive sector filter excludes the null-sector row.
    assert all(
        a.ticker != "COIN"
        for a in service.list_assets(db_session, sectors=["technology"])
    )


def test_list_assets_sector_composes_with_category_and_search(
    db_session: Session,
) -> None:
    service.add_asset(
        db_session,
        "STKF",
        _eligible_provider(
            quote_type="EQUITY",
            company_name="Apex Bank",
            sector_key="financial-services",
        ),
    )
    service.add_asset(
        db_session,
        "STKT",
        _eligible_provider(
            quote_type="EQUITY",
            company_name="Apex Chips",
            sector_key="technology",
        ),
    )
    service.add_asset(
        db_session,
        "ETFF",
        _eligible_provider(
            quote_type="ETF",
            company_name="Apex Financials ETF",
            sector_key="financial-services",
        ),
    )

    # search "apex" matches all three; category=stock narrows to STKF/STKT;
    # sector=financial-services narrows to STKF alone.
    result = service.list_assets(
        db_session,
        search="apex",
        categories=["stock"],
        sectors=["financial-services"],
    )
    assert [a.ticker for a in result] == ["STKF"]
    assert (
        service.count_assets(
            db_session,
            search="apex",
            categories=["stock"],
            sectors=["financial-services"],
        )
        == 1
    )


def test_count_assets_matches_category_and_search_compose(
    db_session: Session,
) -> None:
    service.add_asset(
        db_session,
        "STKA",
        _eligible_provider(quote_type="EQUITY", company_name="Apex"),
    )
    service.add_asset(
        db_session,
        "STKB",
        _eligible_provider(quote_type="EQUITY", company_name="Zenith"),
    )
    service.add_asset(
        db_session,
        "BTC",
        _eligible_provider(quote_type="CRYPTOCURRENCY", company_name="Apex Coin"),
    )

    assert service.count_assets(db_session) == 3
    assert service.count_assets(db_session, categories=["stock"]) == 2
    assert service.count_assets(db_session, categories=["fund"]) == 0
    # Search AND category compose: "apex" matches STKA and BTC, category narrows to stock.
    assert (
        service.count_assets(db_session, search="apex", categories=["stock"]) == 1
    )


def test_list_assets_search_by_ticker_or_name(db_session: Session) -> None:
    service.add_asset(
        db_session, "TSCO", _eligible_provider(company_name="Tesco PLC")
    )
    service.add_asset(
        db_session, "AAPL", _eligible_provider(company_name="Apple Inc.")
    )

    by_ticker = service.list_assets(db_session, search="tsc")
    assert [a.ticker for a in by_ticker] == ["TSCO"]

    by_name = service.list_assets(db_session, search="apple")
    assert [a.ticker for a in by_name] == ["AAPL"]


def test_count_assets_matches_filter(db_session: Session) -> None:
    for ticker in ("AMZN", "AAPL", "MSFT"):
        service.add_asset(db_session, ticker, _eligible_provider())

    assert service.count_assets(db_session) == 3
    assert service.count_assets(db_session, search="a") == 2  # AMZN, AAPL
    assert service.count_assets(db_session, search="zzz") == 0


def test_delete_asset_returns_existence(db_session: Session) -> None:
    asset = service.add_asset(db_session, "DEL", _eligible_provider())

    assert service.delete_asset(db_session, asset.id) is True
    assert service.delete_asset(db_session, asset.id) is False


def test_get_asset_detail_unknown_ticker_raises(db_session: Session) -> None:
    with pytest.raises(AssetNotFoundError):
        service.get_asset_detail(db_session, "NOPE", _detail_provider())


def test_get_asset_detail_cache_miss_fetches_and_stores(
    db_session: Session,
) -> None:
    asset = service.add_asset(db_session, "DTL", _eligible_provider())
    provider = _detail_provider()

    result = service.get_asset_detail(
        db_session, "dtl", provider, today=date(2026, 8, 29)
    )

    assert provider.detail_calls == 1
    assert result.asset.id == asset.id
    assert result.snapshot.snapshot_date == date(2026, 8, 29)
    assert result.snapshot.currency == asset.currency
    assert result.snapshot.current_price == 191.0
    assert result.snapshot.previous_close == 188.0
    assert result.snapshot.price_history == [
        {"date": "2024-01-02", "close": 180.0},
        {"date": "2024-01-03", "close": 185.0},
    ]
    assert _count_snapshots(db_session, asset.id) == 1


def test_get_asset_detail_sources_profile_from_asset_and_volumes_from_snapshot(
    db_session: Session,
) -> None:
    # Profile fields are populated on the asset at add time; the snapshot only
    # carries the time-varying volumes.
    asset = service.add_asset(
        db_session,
        "CO",
        _eligible_provider(
            country="United States",
            city="Cupertino",
            employees=164_000,
            website="https://apple.com",
        ),
    )
    provider = _detail_provider()
    provider._detail = AssetDetailData(
        current_price=191.0,
        previous_close=188.0,
        short_description="A canned description.",
        price_history=[HistoryBar(date=date(2024, 1, 2), close=180.0, volume=1.0)],
        volume=52_140_300,
        avg_volume=58_910_000,
    )
    today = date(2026, 8, 29)

    result = service.get_asset_detail(db_session, "CO", provider, today=today)

    # Profile from the asset.
    assert result.asset.country == "United States"
    assert result.asset.city == "Cupertino"
    assert result.asset.employees == 164_000
    assert result.asset.website == "https://apple.com"
    # Volumes from the snapshot.
    assert result.snapshot.volume == 52_140_300
    assert result.snapshot.avg_volume == 58_910_000

    # Same-day serve returns the stored volumes without re-fetching.
    served = service.get_asset_detail(db_session, "CO", provider, today=today)
    assert provider.detail_calls == 1
    assert served.snapshot.avg_volume == 58_910_000
    assert _count_snapshots(db_session, asset.id) == 1


def test_get_asset_detail_absent_profile_and_volumes_are_none(
    db_session: Session,
) -> None:
    # Provider omits the profile fields at add time and the volumes at fetch
    # time: the asset's profile and the snapshot's volumes are all NULL.
    service.add_asset(db_session, "NULLCO", _eligible_provider())
    provider = _detail_provider()

    result = service.get_asset_detail(
        db_session, "NULLCO", provider, today=date(2026, 8, 29)
    )

    assert result.asset.country is None
    assert result.asset.city is None
    assert result.asset.employees is None
    assert result.asset.website is None
    assert result.snapshot.volume is None
    assert result.snapshot.avg_volume is None


def test_get_asset_detail_cache_hit_does_not_call_provider(
    db_session: Session,
) -> None:
    asset = service.add_asset(db_session, "HIT", _eligible_provider())
    provider = _detail_provider()
    today = date(2026, 8, 29)

    service.get_asset_detail(db_session, "HIT", provider, today=today)
    assert provider.detail_calls == 1

    result = service.get_asset_detail(db_session, "HIT", provider, today=today)

    assert provider.detail_calls == 1  # not called again
    assert result.snapshot.snapshot_date == today
    assert _count_snapshots(db_session, asset.id) == 1


def test_get_asset_detail_new_day_fetches_fresh_snapshot(
    db_session: Session,
) -> None:
    asset = service.add_asset(db_session, "DAY", _eligible_provider())
    provider = _detail_provider()

    service.get_asset_detail(db_session, "DAY", provider, today=date(2026, 8, 28))
    result = service.get_asset_detail(
        db_session, "DAY", provider, today=date(2026, 8, 29)
    )

    assert provider.detail_calls == 2
    assert result.snapshot.snapshot_date == date(2026, 8, 29)
    assert _count_snapshots(db_session, asset.id) == 2


def test_get_asset_detail_fetch_fails_no_today_row_raises_and_no_persist(
    db_session: Session,
) -> None:
    asset = service.add_asset(db_session, "ERR", _eligible_provider())

    # An older-day snapshot exists but must NOT be served on a fresh-fetch fail.
    ok_provider = _detail_provider()
    service.get_asset_detail(
        db_session, "ERR", ok_provider, today=date(2026, 8, 27)
    )
    assert _count_snapshots(db_session, asset.id) == 1

    failing = _eligible_provider()
    failing._detail_error = MarketDataUnavailableError("detail down")

    with pytest.raises(MarketDataUnavailableError):
        service.get_asset_detail(
            db_session, "ERR", failing, today=date(2026, 8, 29)
        )

    # No new row for today; the older row is untouched.
    assert _count_snapshots(db_session, asset.id) == 1
