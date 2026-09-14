"""TestClient tests for the assets API using a fake provider (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from tests.fakes import FakeMarketDataProvider

from cadence.api.app import app
from cadence.api.routers.assets import get_market_data_provider
from cadence.assets.errors import (
    MarketDataUnavailableError,
    UnknownTickerError,
)
from cadence.assets.market_data import AssetDetailData, AssetInfo, HistoryBar

_EXPECTED_CRITERIA = {"price", "avg_daily_turnover", "market_cap", "history"}

_DETAIL_KEYS = {
    "ticker",
    "name",
    "category",
    "sector",
    "exchange",
    "currency",
    "current_price",
    "previous_close",
    "short_description",
    "country",
    "city",
    "employees",
    "website",
    "volume",
    "avg_volume",
    "price_history",
    "snapshot_date",
}


def _detail_provider() -> FakeMarketDataProvider:
    # Profile fields are populated on the asset at add time (via the info); the
    # snapshot only carries the time-varying volumes.
    provider = _eligible_provider(
        country="United States",
        city="Cupertino",
        employees=164_000,
        website="https://apple.com",
    )
    provider._detail = AssetDetailData(
        current_price=191.0,
        previous_close=188.0,
        short_description="A canned description.",
        price_history=[
            HistoryBar(date=date(2024, 1, 2), close=180.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 3), close=185.0, volume=1_100_000.0),
        ],
        volume=52_140_300,
        avg_volume=58_910_000,
    )
    return provider


def _eligible_provider(
    quote_type: str = "EQUITY",
    company_name: str = "Apple Inc.",
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
            exchange="NASDAQ",
            currency="EUR",
            price=190.0,
            market_cap=3_000_000_000_000.0,
            quote_type=quote_type,
            sector_key=sector_key,
            country=country,
            city=city,
            employees=employees,
            website=website,
        ),
        history=[
            HistoryBar(date=date(2000, 1, 1), close=100.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=190.0, volume=1_000_000.0),
        ],
    )


def _add(client: TestClient, ticker: str) -> None:
    """Add one asset, asserting the create succeeded."""
    assert client.post("/api/v1/assets", json={"ticker": ticker}).status_code == 201


def _use_provider(provider: FakeMarketDataProvider) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: provider


def test_create_asset_success(client: TestClient) -> None:
    _use_provider(_eligible_provider())

    response = client.post("/api/v1/assets", json={"ticker": "aapl"})

    assert response.status_code == 201
    body = response.json()
    assert body["ticker"] == "AAPL"  # normalized
    assert body["name"] == "Apple Inc."
    assert body["category"] == "stock"
    assert body["currency"] == "EUR"
    assert body["is_eligible"] is True
    assert set(body.keys()) == {
        "id",
        "ticker",
        "name",
        "category",
        "sector",
        "exchange",
        "currency",
        "market_cap_eur",
        "avg_daily_turnover_eur",
        "history_years",
        "is_eligible",
        "criteria_results",
        "created_at",
    }
    # Sector is present and null-safe: this eligible provider reports no sector.
    assert body["sector"] is None
    names = {c["name"] for c in body["criteria_results"]}
    assert names == _EXPECTED_CRITERIA
    for criterion in body["criteria_results"]:
        assert set(criterion.keys()) == {"name", "passed", "value", "threshold"}


def test_create_asset_classifies_equity_as_stock(client: TestClient) -> None:
    _use_provider(_eligible_provider(quote_type="EQUITY"))

    response = client.post("/api/v1/assets", json={"ticker": "AAPL"})

    assert response.status_code == 201
    assert response.json()["category"] == "stock"


def test_create_asset_classifies_crypto(client: TestClient) -> None:
    _use_provider(_eligible_provider(quote_type="CRYPTOCURRENCY"))

    response = client.post("/api/v1/assets", json={"ticker": "BTC-USD"})

    assert response.status_code == 201
    assert response.json()["category"] == "crypto"


def test_create_asset_exposes_populated_sector(client: TestClient) -> None:
    _use_provider(_eligible_provider(sector_key="financial-services"))

    response = client.post("/api/v1/assets", json={"ticker": "JPM"})

    assert response.status_code == 201
    assert response.json()["sector"] == "financial-services"


def test_create_duplicate_returns_409(client: TestClient) -> None:
    _use_provider(_eligible_provider())

    first = client.post("/api/v1/assets", json={"ticker": "AAPL"})
    assert first.status_code == 201

    second = client.post("/api/v1/assets", json={"ticker": "aapl"})
    assert second.status_code == 409


def test_unknown_ticker_returns_422(client: TestClient) -> None:
    provider = FakeMarketDataProvider(
        info_error=UnknownTickerError("no data"),
    )
    _use_provider(provider)

    response = client.post("/api/v1/assets", json={"ticker": "NOPE"})
    assert response.status_code == 422

    # nothing persisted
    listing = client.get("/api/v1/assets")
    assert all(a["ticker"] != "NOPE" for a in listing.json()["items"])


def test_provider_failure_returns_503_without_persisting(
    client: TestClient,
) -> None:
    provider = FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Flaky Co",
            exchange="NYSE",
            currency="USD",
            price=10.0,
            market_cap=2_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=[HistoryBar(date=date(2010, 1, 1), close=10.0, volume=100_000.0)],
        fx_error=MarketDataUnavailableError("fx down"),
    )
    _use_provider(provider)

    response = client.post("/api/v1/assets", json={"ticker": "FLKY"})
    assert response.status_code == 503

    listing = client.get("/api/v1/assets")
    assert all(a["ticker"] != "FLKY" for a in listing.json()["items"])


def test_list_assets_returns_envelope_ticker_asc_by_default(
    client: TestClient,
) -> None:
    _use_provider(_eligible_provider())
    # Add out of order to prove the default sort is ticker asc, not insert order.
    for ticker in ("CCC", "AAA", "BBB"):
        _add(client, ticker)

    response = client.get("/api/v1/assets")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "total"}
    assert body["total"] == 3
    # Default order is ticker ascending.
    assert [a["ticker"] for a in body["items"]] == ["AAA", "BBB", "CCC"]


def test_list_assets_pagination_offset_and_total(client: TestClient) -> None:
    _use_provider(_eligible_provider())
    tickers = [f"T{i:02d}" for i in range(25)]
    for ticker in tickers:
        _add(client, ticker)

    first = client.get("/api/v1/assets", params={"limit": 20, "offset": 0})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["total"] == 25
    assert len(first_body["items"]) == 20
    # ticker asc: T00 up to T19 on the first page.
    assert first_body["items"][0]["ticker"] == "T00"

    second = client.get("/api/v1/assets", params={"limit": 20, "offset": 20})
    second_body = second.json()
    assert second_body["total"] == 25
    assert [a["ticker"] for a in second_body["items"]] == [
        "T20",
        "T21",
        "T22",
        "T23",
        "T24",
    ]


def test_list_assets_sort_ticker_desc(client: TestClient) -> None:
    _use_provider(_eligible_provider())
    for ticker in ("AAA", "BBB", "CCC"):
        _add(client, ticker)

    response = client.get(
        "/api/v1/assets", params={"sort": "ticker", "direction": "desc"}
    )

    assert response.status_code == 200
    assert [a["ticker"] for a in response.json()["items"]] == ["CCC", "BBB", "AAA"]


def test_list_assets_sort_by_name_asc_and_desc(client: TestClient) -> None:
    _use_provider(_eligible_provider(company_name="Charlie"))
    _add(client, "TSCO")
    _use_provider(_eligible_provider(company_name="Alpha"))
    _add(client, "AAPL")
    _use_provider(_eligible_provider(company_name="Bravo"))
    _add(client, "MSFT")

    asc = client.get("/api/v1/assets", params={"sort": "name", "direction": "asc"})
    assert [a["ticker"] for a in asc.json()["items"]] == ["AAPL", "MSFT", "TSCO"]

    desc = client.get(
        "/api/v1/assets", params={"sort": "name", "direction": "desc"}
    )
    assert [a["ticker"] for a in desc.json()["items"]] == ["TSCO", "MSFT", "AAPL"]


def test_list_assets_filter_by_category(client: TestClient) -> None:
    _use_provider(_eligible_provider(quote_type="EQUITY"))
    _add(client, "STK")
    _add(client, "STK2")
    _use_provider(_eligible_provider(quote_type="CRYPTOCURRENCY"))
    _add(client, "BTC")

    only_crypto = client.get("/api/v1/assets", params={"category": "crypto"})
    only_crypto_body = only_crypto.json()
    assert only_crypto_body["total"] == 1
    assert [a["ticker"] for a in only_crypto_body["items"]] == ["BTC"]

    # Repeatable param: stock OR crypto = all three.
    stock_crypto = client.get(
        "/api/v1/assets", params=[("category", "stock"), ("category", "crypto")]
    )
    stock_crypto_body = stock_crypto.json()
    assert stock_crypto_body["total"] == 3
    assert [a["ticker"] for a in stock_crypto_body["items"]] == ["BTC", "STK", "STK2"]

    # No category = all.
    assert client.get("/api/v1/assets").json()["total"] == 3


def test_create_asset_rejects_unsupported_category(client: TestClient) -> None:
    _use_provider(_eligible_provider(quote_type="ETF"))

    response = client.post("/api/v1/assets", json={"ticker": "ETFX"})
    assert response.status_code == 422

    # Nothing persisted.
    listing = client.get("/api/v1/assets")
    assert all(a["ticker"] != "ETFX" for a in listing.json()["items"])


def test_list_assets_filter_by_sector(client: TestClient) -> None:
    _use_provider(_eligible_provider(sector_key="financial-services"))
    _add(client, "BANK")
    _use_provider(_eligible_provider(sector_key="technology"))
    _add(client, "CHIP")
    _use_provider(_eligible_provider(sector_key="healthcare"))
    _add(client, "DRUG")
    # Null-sector asset must never match a positive sector filter.
    _use_provider(_eligible_provider(quote_type="CRYPTOCURRENCY"))
    _add(client, "COIN")

    only_fin = client.get(
        "/api/v1/assets", params={"sector": "financial-services"}
    )
    only_fin_body = only_fin.json()
    assert only_fin_body["total"] == 1
    assert [a["ticker"] for a in only_fin_body["items"]] == ["BANK"]

    # Repeatable param: financial-services OR technology.
    fin_tech = client.get(
        "/api/v1/assets",
        params=[
            ("sector", "financial-services"),
            ("sector", "technology"),
        ],
    )
    fin_tech_body = fin_tech.json()
    assert fin_tech_body["total"] == 2
    assert [a["ticker"] for a in fin_tech_body["items"]] == ["BANK", "CHIP"]

    # No sector = all (including the null-sector COIN).
    assert client.get("/api/v1/assets").json()["total"] == 4


def test_list_assets_sector_composes_with_category_and_search(
    client: TestClient,
) -> None:
    _use_provider(
        _eligible_provider(
            quote_type="EQUITY",
            company_name="Apex Bank",
            sector_key="financial-services",
        )
    )
    _add(client, "STKF")
    _use_provider(
        _eligible_provider(
            quote_type="EQUITY",
            company_name="Apex Chips",
            sector_key="technology",
        )
    )
    _add(client, "STKT")
    _use_provider(
        _eligible_provider(
            quote_type="CRYPTOCURRENCY",
            company_name="Apex Coin",
        )
    )
    _add(client, "BTCX")

    response = client.get(
        "/api/v1/assets",
        params={
            "search": "apex",
            "category": "stock",
            "sector": "financial-services",
        },
    )
    body = response.json()
    assert body["total"] == 1
    assert [a["ticker"] for a in body["items"]] == ["STKF"]


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("sort", "bogus"),
        ("sort", "market_cap"),
        ("direction", "sideways"),
        ("category", "equities"),
        ("sector", "financials"),
        ("sector", "tech"),
    ],
)
def test_list_assets_invalid_sort_filter_returns_422(
    client: TestClient, param: str, value: str
) -> None:
    response = client.get("/api/v1/assets", params={param: value})
    assert response.status_code == 422


def test_list_assets_sort_filter_search_compose_across_pages(
    client: TestClient,
) -> None:
    _use_provider(_eligible_provider(quote_type="EQUITY", company_name="Apex"))
    _add(client, "STKA")
    _use_provider(_eligible_provider(quote_type="EQUITY", company_name="Zenith"))
    _add(client, "STKB")
    _use_provider(
        _eligible_provider(quote_type="CRYPTOCURRENCY", company_name="Apex Coin")
    )
    _add(client, "BTC")

    # search "apex" matches STKA/BTC; category stock+crypto keeps both (STKB is
    # excluded by the search). sort name desc -> "Apex Coin" (BTC) before "Apex"
    # (STKA). Paginate limit=20.
    base = {
        "search": "apex",
        "category": ["stock", "crypto"],
        "sort": "name",
        "direction": "desc",
    }
    full = client.get("/api/v1/assets", params={**base})
    full_body = full.json()
    assert full_body["total"] == 2
    assert [a["ticker"] for a in full_body["items"]] == ["BTC", "STKA"]

    # total is stable across offsets; page slices are consistent with the order.
    page1 = client.get("/api/v1/assets", params={**base, "limit": 20, "offset": 0})
    assert page1.json()["total"] == 2
    assert [a["ticker"] for a in page1.json()["items"]] == ["BTC", "STKA"]

    page2 = client.get("/api/v1/assets", params={**base, "limit": 20, "offset": 2})
    assert page2.json()["total"] == 2
    assert page2.json()["items"] == []


@pytest.mark.parametrize("page_size", [20, 50, 100])
def test_list_assets_allowed_page_sizes(
    client: TestClient, page_size: int
) -> None:
    _use_provider(_eligible_provider())
    _add(client, "AAPL")

    response = client.get("/api/v1/assets", params={"limit": page_size})

    assert response.status_code == 200
    assert response.json()["total"] == 1


@pytest.mark.parametrize("bad_limit", [1, 10, 30, 200])
def test_list_assets_invalid_limit_returns_422(
    client: TestClient, bad_limit: int
) -> None:
    response = client.get("/api/v1/assets", params={"limit": bad_limit})
    assert response.status_code == 422


def test_list_assets_negative_offset_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/assets", params={"offset": -1})
    assert response.status_code == 422


def test_list_assets_search_by_ticker(client: TestClient) -> None:
    _use_provider(_eligible_provider())
    for ticker in ("AAPL", "AMZN", "MSFT"):
        _add(client, ticker)

    response = client.get("/api/v1/assets", params={"search": "am"})

    body = response.json()
    assert body["total"] == 1
    assert [a["ticker"] for a in body["items"]] == ["AMZN"]


def test_list_assets_search_by_name(client: TestClient) -> None:
    _use_provider(_eligible_provider(company_name="Tesco PLC"))
    _add(client, "TSCO")
    _use_provider(_eligible_provider(company_name="Apple Inc."))
    _add(client, "AAPL")

    response = client.get("/api/v1/assets", params={"search": "tesco"})

    body = response.json()
    assert body["total"] == 1
    assert [a["ticker"] for a in body["items"]] == ["TSCO"]


def test_list_assets_search_wildcard_is_literal(client: TestClient) -> None:
    _use_provider(_eligible_provider())
    for ticker in ("AAPL", "MSFT"):
        _add(client, ticker)

    # '%' would match everything if treated as a LIKE wildcard; here it is
    # escaped, so no ticker/name literally contains it.
    response = client.get("/api/v1/assets", params={"search": "%"})

    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_delete_asset_then_404(client: TestClient) -> None:
    _use_provider(_eligible_provider())
    created = client.post("/api/v1/assets", json={"ticker": "AAPL"})
    asset_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/assets/{asset_id}")
    assert deleted.status_code == 204

    missing = client.delete(f"/api/v1/assets/{asset_id}")
    assert missing.status_code == 404


def test_get_asset_details_success(client: TestClient) -> None:
    _use_provider(_detail_provider())
    client.post("/api/v1/assets", json={"ticker": "AAPL"})

    response = client.get("/api/v1/assets/aapl/details")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == _DETAIL_KEYS
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."
    assert body["category"] == "stock"
    assert body["currency"] == "EUR"
    assert body["current_price"] == 191.0
    assert body["previous_close"] == 188.0
    # Company Information panel fields.
    assert body["exchange"] == "NASDAQ"
    assert body["country"] == "United States"
    assert body["city"] == "Cupertino"
    assert body["employees"] == 164_000
    assert body["website"] == "https://apple.com"
    assert body["volume"] == 52_140_300
    assert body["avg_volume"] == 58_910_000
    assert body["price_history"] == [
        {"date": "2024-01-02", "close": 180.0},
        {"date": "2024-01-03", "close": 185.0},
    ]
    for point in body["price_history"]:
        assert set(point.keys()) == {"date", "close"}


def test_get_asset_details_absent_company_fields_serve_null(
    client: TestClient,
) -> None:
    # Provider omits the profile fields at add time and the volumes at fetch
    # time: all six panel fields serve as null.
    provider = _eligible_provider()
    provider._detail = AssetDetailData(
        current_price=191.0,
        previous_close=188.0,
        short_description="A canned description.",
        price_history=[
            HistoryBar(date=date(2024, 1, 2), close=180.0, volume=1_000_000.0),
        ],
    )
    _use_provider(provider)
    client.post("/api/v1/assets", json={"ticker": "AAPL"})

    response = client.get("/api/v1/assets/aapl/details")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == _DETAIL_KEYS
    for field in ("country", "city", "employees", "website", "volume", "avg_volume"):
        assert body[field] is None


def test_get_asset_details_unknown_ticker_returns_404(
    client: TestClient,
) -> None:
    _use_provider(_detail_provider())

    response = client.get("/api/v1/assets/UNKNOWN/details")

    assert response.status_code == 404


def test_get_asset_details_fetch_failure_returns_503(
    client: TestClient,
) -> None:
    provider = _eligible_provider()
    client_provider = provider
    _use_provider(client_provider)
    client.post("/api/v1/assets", json={"ticker": "AAPL"})

    provider._detail_error = MarketDataUnavailableError("detail down")

    response = client.get("/api/v1/assets/AAPL/details")

    assert response.status_code == 503


@pytest.fixture(autouse=True)
def _clear_provider_override() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_market_data_provider, None)
