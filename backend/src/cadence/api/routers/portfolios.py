"""Portfolios resource router. Mounted under ``/api/v1``."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cadence.api.schemas import (
    PortfolioCreate,
    PortfolioListResponse,
    PortfolioRead,
)
from cadence.database import get_db
from cadence.portfolios import service
from cadence.portfolios.errors import (
    PortfolioNotArchivableError,
    PortfolioNotFoundError,
    PortfolioValidationError,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(payload: PortfolioCreate, db: DbSession) -> PortfolioRead:
    """Create a portfolio, normalizing and validating its tickers."""
    try:
        portfolio = service.create_portfolio(
            db,
            name=payload.name,
            stocks=payload.stocks,
            source=payload.source,
            description=payload.description,
            risk_profile=payload.risk_profile,
            max_allocation_pct=payload.max_allocation_pct,
            source_run_id=payload.source_run_id,
        )
    except PortfolioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PortfolioRead.model_validate(portfolio)


@router.get("", response_model=PortfolioListResponse)
def list_portfolios(
    db: DbSession,
    include_legacy: bool = True,
    include_archived: bool = False,
    limit: int = 50,
) -> PortfolioListResponse:
    """Return stored portfolios, newest first."""
    items = [
        PortfolioRead.model_validate(portfolio)
        for portfolio in service.list_portfolios(
            db,
            limit=limit,
            include_legacy=include_legacy,
            include_archived=include_archived,
        )
    ]
    total = service.count_portfolios(
        db, include_legacy=include_legacy, include_archived=include_archived
    )
    return PortfolioListResponse(items=items, total=total)


@router.get("/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(portfolio_id: uuid.UUID, db: DbSession) -> PortfolioRead:
    """Return a single portfolio by id."""
    try:
        portfolio = service.get_portfolio(db, portfolio_id)
    except PortfolioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return PortfolioRead.model_validate(portfolio)


@router.post("/{portfolio_id}/archive", response_model=PortfolioRead)
def archive_portfolio(portfolio_id: uuid.UUID, db: DbSession) -> PortfolioRead:
    """Soft-archive a portfolio (409 if it has an active or paused session)."""
    try:
        portfolio = service.archive_portfolio(db, portfolio_id)
    except PortfolioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except PortfolioNotArchivableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return PortfolioRead.model_validate(portfolio)


@router.post("/{portfolio_id}/unarchive", response_model=PortfolioRead)
def unarchive_portfolio(portfolio_id: uuid.UUID, db: DbSession) -> PortfolioRead:
    """Restore an archived portfolio to the default listing."""
    try:
        portfolio = service.unarchive_portfolio(db, portfolio_id)
    except PortfolioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return PortfolioRead.model_validate(portfolio)
