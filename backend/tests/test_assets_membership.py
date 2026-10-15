"""Membership isolation: watchlist assets never leak into universe reads.

The watchlist shares the ``assets`` table with the tradable universe, separated
only by the ``membership`` column. Every trading/analytics read must default to
``UNIVERSE`` so a watchlist candidate is invisible to build/rebalance/evaluation
while remaining directly readable by id/ticker.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.fakes import FakeBroker, FakeMarketDataProvider

from cadence.assets import service
from cadence.assets.category import AssetMembership
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.assets.models import Asset


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


def _broker() -> FakeBroker:
    return FakeBroker()


def _seed(db_session: Session) -> None:
    """One universe member (UNI) and one watchlist member (WATCH)."""
    service.add_asset(db_session, "UNI", _provider(), _broker())
    service.add_asset(
        db_session,
        "WATCH",
        _provider(),
        _broker(),
        membership=AssetMembership.WATCHLIST,
    )


def test_list_assets_defaults_to_universe_only(db_session: Session) -> None:
    _seed(db_session)
    # The default (no membership arg) is exactly what build/rebalance call.
    assert [a.ticker for a in service.list_assets(db_session)] == ["UNI"]
    assert service.count_assets(db_session) == 1


def test_list_assets_membership_none_returns_all(db_session: Session) -> None:
    _seed(db_session)
    tickers = {a.ticker for a in service.list_assets(db_session, membership=None)}
    assert tickers == {"UNI", "WATCH"}
    assert service.count_assets(db_session, membership=None) == 2


def test_list_assets_membership_watchlist_returns_only_watchlist(
    db_session: Session,
) -> None:
    _seed(db_session)
    assert [
        a.ticker
        for a in service.list_assets(
            db_session, membership=AssetMembership.WATCHLIST
        )
    ] == ["WATCH"]
    assert (
        service.count_assets(db_session, membership=AssetMembership.WATCHLIST) == 1
    )


def test_get_universe_assets_excludes_watchlist(db_session: Session) -> None:
    _seed(db_session)
    assert [a.ticker for a in service.get_universe_assets(db_session)] == ["UNI"]


def test_watchlist_asset_absent_from_candidates_but_readable_directly(
    db_session: Session,
) -> None:
    _seed(db_session)
    # Absent from the candidate read the AI build/rebalance flows use.
    universe = {a.ticker for a in service.list_assets(db_session)}
    assert "WATCH" not in universe
    # Still a real row, directly readable by ticker.
    watch = db_session.scalars(
        select(Asset).where(Asset.ticker == "WATCH")
    ).one()
    assert watch.membership == AssetMembership.WATCHLIST.value
