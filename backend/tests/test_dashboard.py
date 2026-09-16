"""Integration tests for the dashboard aggregation against Postgres.

Covers the two documented states: an empty database (all metrics zero/empty, not
an error) and a seeded universe (assets of varied categories/sectors with an
eligible/ineligible split, a portfolio, and an active session with trades),
asserting every count is correct — through both the service and the HTTP layer.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeBroker, FakeMarketDataProvider

from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.broker.models import OrderSide
from cadence.dashboard import service
from cadence.paper_trading import service as paper_trading_service
from cadence.portfolios import service as portfolios_service


def _provider(
    *,
    quote_type: str = "EQUITY",
    sector_key: str | None = "technology",
    country: str | None = "Germany",
    market_cap: float = 5_000_000_000.0,
) -> FakeMarketDataProvider:
    """A market-data provider yielding one eligible-by-default asset profile."""
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Co",
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=market_cap,
            quote_type=quote_type,
            sector_key=sector_key,
            country=country,
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _broker() -> FakeBroker:
    return FakeBroker()


def _seed_universe(db_session: Session) -> None:
    """Seed four assets: three eligible (varied category/sector) + one ineligible."""
    assets_service.add_asset(
        db_session, "TECH", _provider(sector_key="technology"), _broker()
    )
    assets_service.add_asset(
        db_session,
        "FIN",
        _provider(sector_key="financial-services", country="USA"),
        _broker(),
    )
    # A crypto asset has no sector; still eligible.
    assets_service.add_asset(
        db_session,
        "BTC-USD",
        _provider(quote_type="CRYPTOCURRENCY", sector_key=None, country="Ireland"),
        _broker(),
    )
    # Below the market-cap threshold -> ineligible, but still stored.
    assets_service.add_asset(
        db_session,
        "SMALL",
        _provider(sector_key="technology", market_cap=100_000_000.0),
        _broker(),
    )


def _seed_activity(db_session: Session) -> None:
    """Seed a portfolio and an active paper-trading session with two trades."""
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["TECH", "FIN"]
    )
    session_row = paper_trading_service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
    for ticker in ("TECH", "FIN"):
        paper_trading_service.record_trade(
            db_session,
            session_id=session_row.id,
            ticker=ticker,
            side=OrderSide.BUY,
            quantity=10.0,
            price=50.0,
            signal_type="entry",
        )


# --- empty database ---------------------------------------------------------


def test_metrics_empty_database_are_zero(db_session: Session) -> None:
    metrics = service.get_dashboard_metrics(db_session)

    assert metrics.assets.total == 0
    assert metrics.assets.eligible == 0
    assert metrics.assets.ineligible == 0
    assert metrics.assets.by_category == []
    assert metrics.assets.by_sector == []
    assert metrics.portfolio_count == 0
    assert metrics.paper_trading.active_sessions == 0
    assert metrics.paper_trading.recent_trades == 0


def test_metrics_endpoint_empty_database(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["assets"] == {
        "total": 0,
        "eligible": 0,
        "ineligible": 0,
        "by_category": [],
        "by_sector": [],
    }
    assert body["portfolio_count"] == 0
    assert body["paper_trading"] == {"active_sessions": 0, "recent_trades": 0}


# --- seeded universe --------------------------------------------------------


def test_metrics_reflect_seeded_data(db_session: Session) -> None:
    _seed_universe(db_session)
    _seed_activity(db_session)

    metrics = service.get_dashboard_metrics(db_session)

    assert metrics.assets.total == 4
    assert metrics.assets.eligible == 3
    assert metrics.assets.ineligible == 1

    by_category = {e.key: e.count for e in metrics.assets.by_category}
    assert by_category == {"stock": 3, "crypto": 1}

    by_sector = {e.key: e.count for e in metrics.assets.by_sector}
    assert by_sector == {
        "technology": 2,
        "financial-services": 1,
        "no sector": 1,
    }

    assert metrics.portfolio_count == 1
    assert metrics.paper_trading.active_sessions == 1
    assert metrics.paper_trading.recent_trades == 2


def test_metrics_endpoint_reflects_seeded_data(
    client: TestClient, db_session: Session
) -> None:
    _seed_universe(db_session)
    _seed_activity(db_session)

    response = client.get("/api/v1/dashboard/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["assets"]["total"] == 4
    assert body["assets"]["eligible"] == 3
    assert body["assets"]["ineligible"] == 1
    assert body["portfolio_count"] == 1
    assert body["paper_trading"] == {"active_sessions": 1, "recent_trades": 2}
    # Breakdowns are ordered by descending count, then key.
    assert body["assets"]["by_category"][0] == {"key": "stock", "count": 3}
