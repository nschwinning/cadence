"""Integration tests for the portfolios service against Postgres."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import Benchmark, SessionStatus
from cadence.portfolios import service
from cadence.portfolios.constants import PortfolioSource, RiskProfile
from cadence.portfolios.errors import (
    PortfolioNotArchivableError,
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


# --------------------------------------------------------------------------- #
# Archiving
# --------------------------------------------------------------------------- #


def _session(
    db_session: Session,
    portfolio_id: uuid.UUID,
    *,
    strategy_key: str,
    status: SessionStatus | None = None,
) -> None:
    sess = paper_service.create_session(
        db_session, portfolio_id=portfolio_id, strategy_key=strategy_key, rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    if status is not None:
        paper_service.update_session_status(db_session, sess.id, status)


def test_archive_portfolio_with_no_sessions(db_session: Session) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    archived = service.archive_portfolio(db_session, portfolio.id)
    assert archived.archived_at is not None


def test_archive_portfolio_with_only_stopped_sessions(
    db_session: Session,
) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    _session(
        db_session, portfolio.id, strategy_key="s", status=SessionStatus.STOPPED
    )
    archived = service.archive_portfolio(db_session, portfolio.id)
    assert archived.archived_at is not None


def test_archive_portfolio_rejected_with_active_session(
    db_session: Session,
) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    _session(db_session, portfolio.id, strategy_key="active")
    with pytest.raises(PortfolioNotArchivableError):
        service.archive_portfolio(db_session, portfolio.id)


def test_archive_portfolio_rejected_with_paused_session(
    db_session: Session,
) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    _session(
        db_session, portfolio.id, strategy_key="p", status=SessionStatus.PAUSED
    )
    with pytest.raises(PortfolioNotArchivableError):
        service.archive_portfolio(db_session, portfolio.id)


def test_unarchive_portfolio_clears_timestamp(db_session: Session) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    service.archive_portfolio(db_session, portfolio.id)
    restored = service.unarchive_portfolio(db_session, portfolio.id)
    assert restored.archived_at is None


def test_default_portfolio_list_hides_archived(db_session: Session) -> None:
    portfolio = service.create_portfolio(db_session, name="P", stocks=["AAPL"])
    service.archive_portfolio(db_session, portfolio.id)

    visible_ids = [p.id for p in service.list_portfolios(db_session)]
    assert portfolio.id not in visible_ids

    with_archived = [
        p.id
        for p in service.list_portfolios(db_session, include_archived=True)
    ]
    assert portfolio.id in with_archived


def test_archive_unknown_portfolio_raises(db_session: Session) -> None:
    with pytest.raises(PortfolioNotFoundError):
        service.archive_portfolio(db_session, uuid.uuid4())
    with pytest.raises(PortfolioNotFoundError):
        service.unarchive_portfolio(db_session, uuid.uuid4())
