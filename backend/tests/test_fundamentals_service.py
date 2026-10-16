"""Tests for ``record_fundamentals`` (fake provider, no network).

The helper is best-effort: it always leaves exactly one ``asset_fundamentals``
row and never raises, so a failed fetch can never fail the watchlist add that
triggered it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.fakes import FakeBroker, FakeFundamentalsProvider, FakeMarketDataProvider

from cadence.assets import service
from cadence.assets.category import AssetCategory, AssetMembership
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


# --- Batch refresh: refresh_stock_fundamentals -----------------------------


def _make_asset(
    db_session: Session,
    ticker: str,
    category: AssetCategory = AssetCategory.STOCK,
) -> Asset:
    """Insert a bare asset row of ``category`` directly (no provider needed)."""
    asset = Asset(
        ticker=ticker,
        name=f"{ticker} Co",
        alpaca_symbol=ticker,
        fractionable=True,
        category=category.value,
        sector="technology" if category is AssetCategory.STOCK else None,
        exchange="NASDAQ",
        currency="USD",
        country="United States",
        is_eligible=True,
        market_cap_usd=5_000_000_000.0,
        avg_daily_turnover_usd=10_000_000.0,
        history_years=10.0,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _available(cik: str) -> Fundamentals:
    return Fundamentals(
        status=FundamentalsStatus.AVAILABLE,
        source=SOURCE_SEC_EDGAR,
        cik=cik,
        document={"figures": {"revenue": {"value": 1.0}}},
    )


def test_refresh_excludes_crypto_and_fetches_only_stocks(db_session: Session) -> None:
    _make_asset(db_session, "AAA", AssetCategory.STOCK)
    _make_asset(db_session, "BBB", AssetCategory.STOCK)
    _make_asset(db_session, "DOGE", AssetCategory.CRYPTO)
    provider = FakeFundamentalsProvider(
        by_ticker={"AAA": _available("1"), "BBB": _available("2")}
    )

    summary = service.refresh_stock_fundamentals(db_session, provider)

    # Only the two stocks were fetched, in deterministic ticker order; crypto skipped.
    assert provider.fetch_calls == ["AAA", "BBB"]
    assert summary.stocks_considered == 2
    assert summary.refreshed == 2
    assert summary.available == 2
    # No fundamentals row was created for the crypto asset.
    crypto = db_session.scalars(
        select(Asset).where(Asset.ticker == "DOGE")
    ).one()
    assert (
        db_session.scalars(
            select(AssetFundamentals).where(
                AssetFundamentals.asset_id == crypto.id
            )
        ).first()
        is None
    )


def test_refresh_upserts_each_stock_and_advances_fetched_at(
    db_session: Session,
) -> None:
    asset = _make_asset(db_session, "AAA", AssetCategory.STOCK)
    # Seed a pre-existing fundamentals row with an old fetched_at.
    stale = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.add(
        AssetFundamentals(
            asset_id=asset.id,
            source=SOURCE_SEC_EDGAR,
            status=FundamentalsStatus.UNAVAILABLE.value,
            cik=None,
            document={},
            fetched_at=stale,
        )
    )
    db_session.commit()

    provider = FakeFundamentalsProvider(by_ticker={"AAA": _available("1")})
    service.refresh_stock_fundamentals(db_session, provider)

    rows = db_session.scalars(
        select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
    ).all()
    # Still a single row (upsert), now carrying the fresh data and an advanced time.
    assert len(rows) == 1
    assert rows[0].status == FundamentalsStatus.AVAILABLE.value
    assert rows[0].cik == "1"
    assert rows[0].fetched_at.replace(tzinfo=UTC) > stale


def test_refresh_refetches_all_stocks_ignoring_recency(db_session: Session) -> None:
    # A stock whose fundamentals were "just" fetched is still re-fetched: there is
    # no staleness skip — every run refreshes all stocks.
    asset = _make_asset(db_session, "AAA", AssetCategory.STOCK)
    db_session.add(
        AssetFundamentals(
            asset_id=asset.id,
            source=SOURCE_SEC_EDGAR,
            status=FundamentalsStatus.AVAILABLE.value,
            cik="old",
            document={"figures": {}},
            fetched_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    provider = FakeFundamentalsProvider(by_ticker={"AAA": _available("new")})
    summary = service.refresh_stock_fundamentals(db_session, provider)

    assert provider.fetch_calls == ["AAA"]
    assert summary.refreshed == 1
    row = db_session.scalars(
        select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
    ).one()
    assert row.cik == "new"


def test_refresh_is_best_effort_when_one_asset_fails(db_session: Session) -> None:
    _make_asset(db_session, "AAA", AssetCategory.STOCK)
    _make_asset(db_session, "BBB", AssetCategory.STOCK)
    # BBB's fetch raises; AAA succeeds. record_fundamentals swallows the provider
    # error for BBB into an unavailable row, and the batch still refreshes AAA.
    provider = FakeFundamentalsProvider(
        by_ticker={"AAA": _available("1")},
        error_by_ticker={"BBB": RuntimeError("edgar boom")},
    )

    summary = service.refresh_stock_fundamentals(db_session, provider)

    assert provider.fetch_calls == ["AAA", "BBB"]
    assert summary.stocks_considered == 2
    assert summary.refreshed == 2
    assert summary.available == 1
    assert summary.unavailable == 1
    bbb = db_session.scalars(select(Asset).where(Asset.ticker == "BBB")).one()
    bbb_row = db_session.scalars(
        select(AssetFundamentals).where(AssetFundamentals.asset_id == bbb.id)
    ).one()
    assert bbb_row.status == FundamentalsStatus.UNAVAILABLE.value


def test_refresh_summary_counts_by_status(db_session: Session) -> None:
    _make_asset(db_session, "AAA", AssetCategory.STOCK)  # available
    _make_asset(db_session, "BBB", AssetCategory.STOCK)  # partial
    _make_asset(db_session, "CCC", AssetCategory.STOCK)  # unavailable (absent)
    provider = FakeFundamentalsProvider(
        by_ticker={
            "AAA": _available("1"),
            "BBB": Fundamentals(
                status=FundamentalsStatus.PARTIAL,
                source=SOURCE_SEC_EDGAR,
                cik="2",
                document={"figures": {}},
            ),
        }
    )

    summary = service.refresh_stock_fundamentals(db_session, provider)

    assert summary == service.FundamentalsRefreshSummary(
        stocks_considered=3,
        refreshed=3,
        available=1,
        partial=1,
        unavailable=1,
    )


def test_refresh_empty_universe_returns_zero_summary(db_session: Session) -> None:
    provider = FakeFundamentalsProvider()
    summary = service.refresh_stock_fundamentals(db_session, provider)
    assert summary == service.FundamentalsRefreshSummary()
    assert provider.fetch_calls == []
