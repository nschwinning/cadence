"""Portfolios service/repository: business logic and data access.

Routers stay thin and delegate here. All DB access for the portfolios domain
lives in this module. Ticker normalization and validation mirror trading-bot's
``Portfolio`` domain rules (non-empty, upper-cased, de-duplicated).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence.portfolios.constants import LEGACY_SOURCES, PortfolioSource, RiskProfile
from cadence.portfolios.errors import (
    PortfolioNotFoundError,
    PortfolioValidationError,
)
from cadence.portfolios.models import Portfolio

# Bounds on the default listing page size (mirrors trading-bot's clamp).
MIN_LIST_LIMIT = 1
MAX_LIST_LIMIT = 500


def normalize_tickers(tickers: list[str]) -> list[str]:
    """Upper-case, strip, drop blanks, and de-duplicate ``tickers`` in order.

    Raises:
        PortfolioValidationError: if no non-empty ticker remains.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    if not normalized:
        raise PortfolioValidationError("portfolio must contain at least one ticker")
    return normalized


def _validate_allocation(max_allocation_pct: float) -> None:
    if not 0 < max_allocation_pct <= 1.0:
        raise PortfolioValidationError(
            "max_allocation_pct must be between 0 (exclusive) and 1.0 (inclusive)"
        )


def create_portfolio(
    session: Session,
    *,
    name: str,
    stocks: list[str],
    source: PortfolioSource = PortfolioSource.MANUAL,
    description: str | None = None,
    risk_profile: RiskProfile | None = None,
    max_allocation_pct: float = 1.0,
    source_run_id: str | None = None,
) -> Portfolio:
    """Validate the request and insert a portfolio.

    Tickers are normalized (upper-cased, de-duplicated, blanks dropped) and must
    not be empty. ``max_allocation_pct`` must be in ``(0, 1]``.

    Raises:
        PortfolioValidationError: on an empty name, no valid tickers, or an
            out-of-range allocation.
    """
    if not name or not name.strip():
        raise PortfolioValidationError("portfolio name must not be empty")
    _validate_allocation(max_allocation_pct)
    normalized = normalize_tickers(stocks)

    portfolio = Portfolio(
        name=name.strip(),
        description=description,
        stocks=normalized,
        max_allocation_pct=max_allocation_pct,
        source=source.value,
        risk_profile=risk_profile.value if risk_profile else None,
        source_run_id=source_run_id,
    )
    session.add(portfolio)
    session.commit()
    session.refresh(portfolio)
    return portfolio


def get_portfolio(session: Session, portfolio_id: uuid.UUID) -> Portfolio:
    """Return a portfolio by id or raise :class:`PortfolioNotFoundError`."""
    portfolio = session.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise PortfolioNotFoundError(f"Portfolio {portfolio_id} not found")
    return portfolio


def list_portfolios(
    session: Session,
    *,
    limit: int = 50,
    include_legacy: bool = True,
) -> list[Portfolio]:
    """List portfolios newest first, optionally excluding legacy ones."""
    safe_limit = max(MIN_LIST_LIMIT, min(limit, MAX_LIST_LIMIT))
    stmt = select(Portfolio).order_by(
        Portfolio.created_at.desc(), Portfolio.id.desc()
    )
    if not include_legacy:
        stmt = stmt.where(Portfolio.source.not_in([s.value for s in LEGACY_SOURCES]))
    return list(session.execute(stmt.limit(safe_limit)).scalars())


def count_portfolios(session: Session, *, include_legacy: bool = True) -> int:
    """Count stored portfolios (optionally excluding legacy ones)."""
    stmt = select(func.count()).select_from(Portfolio)
    if not include_legacy:
        stmt = stmt.where(Portfolio.source.not_in([s.value for s in LEGACY_SOURCES]))
    return session.execute(stmt).scalar_one()


def update_portfolio_stocks(
    session: Session,
    portfolio_id: uuid.UUID,
    stocks: list[str],
) -> Portfolio:
    """Replace a portfolio's ticker list (used during rebalance).

    Raises:
        PortfolioNotFoundError: if no portfolio has ``portfolio_id``.
        PortfolioValidationError: if the normalized ticker list is empty.
    """
    portfolio = get_portfolio(session, portfolio_id)
    portfolio.stocks = normalize_tickers(stocks)
    session.commit()
    session.refresh(portfolio)
    return portfolio
