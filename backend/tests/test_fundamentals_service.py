"""Tests for ``record_fundamentals`` (fake provider, no network).

The helper is best-effort: it always leaves exactly one ``asset_fundamentals``
row and never raises, so a failed fetch can never fail the watchlist add that
triggered it.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.fakes import FakeBroker, FakeFundamentalsProvider, FakeMarketDataProvider

from cadence.assets import service
from cadence.assets.category import AssetMembership
from cadence.assets.fundamentals import (
    SOURCE_SEC_EDGAR,
    Fundamentals,
    FundamentalsStatus,
    _map_company_facts,
)
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.assets.models import Asset, AssetFundamentals


def _provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Test Co",
            exchange="XETRA",
            currency="USD",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _add_watchlist_asset(db_session: Session, ticker: str = "WATCH") -> Asset:
    return service.add_asset(
        db_session,
        ticker,
        _provider(),
        FakeBroker(),
        membership=AssetMembership.WATCHLIST,
    )


def test_map_company_facts_picks_latest_annual_figures() -> None:
    # Two annual 10-K points for revenue; the later fiscal-year end wins. A
    # non-revenue concept (net income) maps under its own key.
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100,
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2022,
                                "end": "2022-12-31",
                            },
                            {
                                "val": 150,
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2023,
                                "end": "2023-12-31",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 20,
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2023,
                                "end": "2023-12-31",
                            }
                        ]
                    }
                },
            }
        }
    }

    document = _map_company_facts(facts)

    figures = document["figures"]
    assert figures["revenue"]["value"] == 150
    assert figures["revenue"]["period_end"] == "2023-12-31"
    assert figures["net_income"]["value"] == 20
    # A concept with no reported facts is simply absent.
    assert "operating_cash_flow" not in figures


def test_record_fundamentals_maps_and_persists(db_session: Session) -> None:
    asset = _add_watchlist_asset(db_session)
    document = {"figures": {"revenue": {"value": 100.0, "unit": "USD"}}}
    provider = FakeFundamentalsProvider(
        by_ticker={
            "WATCH": Fundamentals(
                status=FundamentalsStatus.AVAILABLE,
                source=SOURCE_SEC_EDGAR,
                cik="0000320193",
                document=document,
            )
        }
    )

    record = service.record_fundamentals(db_session, asset, provider)

    assert provider.fetch_calls == ["WATCH"]
    assert record.status == FundamentalsStatus.AVAILABLE.value
    assert record.source == SOURCE_SEC_EDGAR
    assert record.cik == "0000320193"
    assert record.document == document
    # Exactly one row, linked to the asset.
    rows = db_session.scalars(
        select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
    ).all()
    assert len(rows) == 1


def test_record_fundamentals_missing_cik_is_unavailable(db_session: Session) -> None:
    asset = _add_watchlist_asset(db_session)
    # A ticker absent from the fake map yields the missing-CIK unavailable result.
    provider = FakeFundamentalsProvider()

    record = service.record_fundamentals(db_session, asset, provider)

    assert record.status == FundamentalsStatus.UNAVAILABLE.value
    assert record.cik is None
    assert record.document == {}


def test_record_fundamentals_provider_error_is_unavailable_and_asset_intact(
    db_session: Session,
) -> None:
    asset = _add_watchlist_asset(db_session)
    provider = FakeFundamentalsProvider(error=RuntimeError("edgar boom"))

    record = service.record_fundamentals(db_session, asset, provider)

    # The error is swallowed; an unavailable row is persisted, not an exception.
    assert record.status == FundamentalsStatus.UNAVAILABLE.value
    # The asset itself survives untouched.
    reloaded = db_session.get(Asset, asset.id)
    assert reloaded is not None
    assert reloaded.ticker == "WATCH"


def test_record_fundamentals_upserts_single_row(db_session: Session) -> None:
    asset = _add_watchlist_asset(db_session)
    first = FakeFundamentalsProvider(
        by_ticker={
            "WATCH": Fundamentals(
                status=FundamentalsStatus.PARTIAL,
                source=SOURCE_SEC_EDGAR,
                cik="1",
                document={"figures": {}},
            )
        }
    )
    service.record_fundamentals(db_session, asset, first)

    second = FakeFundamentalsProvider(
        by_ticker={
            "WATCH": Fundamentals(
                status=FundamentalsStatus.AVAILABLE,
                source=SOURCE_SEC_EDGAR,
                cik="2",
                document={"figures": {"revenue": {"value": 1.0}}},
            )
        }
    )
    record = service.record_fundamentals(db_session, asset, second)

    # The row was updated in place, not duplicated.
    assert record.status == FundamentalsStatus.AVAILABLE.value
    assert record.cik == "2"
    rows = db_session.scalars(
        select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
    ).all()
    assert len(rows) == 1
