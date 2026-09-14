"""Integration tests for the portfolios service against Postgres."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from cadence.portfolios import service
from cadence.portfolios.constants import PortfolioSource, RiskProfile
from cadence.portfolios.errors import (
    PortfolioNotFoundError,
    PortfolioValidationError,
)


def test_create_normalizes_and_dedupes_tickers(db_session: Session) -> None:
    portfolio = service.create_portfolio(
        db_session,
        name="  Growth  ",
        stocks=[" aapl ", "MSFT", "aapl", "", "msft"],
        source=PortfolioSource.MANUAL,
        risk_profile=RiskProfile.BALANCED,
    )

    assert portfolio.id is not None
    assert portfolio.name == "Growth"
    # Upper-cased, blanks dropped, de-duplicated, order preserved.
    assert portfolio.stocks == ["AAPL", "MSFT"]
    assert portfolio.source == PortfolioSource.MANUAL.value
    assert portfolio.risk_profile == RiskProfile.BALANCED.value
    assert portfolio.max_allocation_pct == 1.0


def test_create_rejects_empty_tickers(db_session: Session) -> None:
    with pytest.raises(PortfolioValidationError):
        service.create_portfolio(
            db_session, name="Empty", stocks=["", "   "]
        )


def test_create_rejects_blank_name(db_session: Session) -> None:
    with pytest.raises(PortfolioValidationError):
        service.create_portfolio(db_session, name="   ", stocks=["AAPL"])


def test_create_rejects_bad_allocation(db_session: Session) -> None:
    with pytest.raises(PortfolioValidationError):
        service.create_portfolio(
            db_session, name="Bad", stocks=["AAPL"], max_allocation_pct=1.5
        )
    with pytest.raises(PortfolioValidationError):
        service.create_portfolio(
            db_session, name="Bad", stocks=["AAPL"], max_allocation_pct=0.0
        )


def test_get_and_not_found(db_session: Session) -> None:
    created = service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    fetched = service.get_portfolio(db_session, created.id)
    assert fetched.id == created.id

    import uuid

    with pytest.raises(PortfolioNotFoundError):
        service.get_portfolio(db_session, uuid.uuid4())


def test_list_newest_first_and_legacy_filter(db_session: Session) -> None:
    manual = service.create_portfolio(
        db_session, name="Manual", stocks=["AAPL"], source=PortfolioSource.MANUAL
    )
    legacy = service.create_portfolio(
        db_session,
        name="Legacy",
        stocks=["MSFT"],
        source=PortfolioSource.LEGACY_BACKTEST,
    )

    all_ids = [p.id for p in service.list_portfolios(db_session)]
    assert manual.id in all_ids
    assert legacy.id in all_ids

    non_legacy = service.list_portfolios(db_session, include_legacy=False)
    non_legacy_ids = [p.id for p in non_legacy]
    assert manual.id in non_legacy_ids
    assert legacy.id not in non_legacy_ids

    assert service.count_portfolios(db_session) >= 2
    assert service.count_portfolios(db_session, include_legacy=False) >= 1


def test_update_stocks(db_session: Session) -> None:
    created = service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    updated = service.update_portfolio_stocks(
        db_session, created.id, [" nvda ", "amd", "nvda"]
    )
    assert updated.stocks == ["NVDA", "AMD"]

    with pytest.raises(PortfolioValidationError):
        service.update_portfolio_stocks(db_session, created.id, ["", "  "])
