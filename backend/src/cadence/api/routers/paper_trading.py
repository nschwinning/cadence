"""Paper-trading resource router (read-only). Mounted under ``/api/v1``.

Writes to paper-trading tables happen via the ai_portfolio flow (built later);
this router only exposes reads: session listing and a session's trades, run
history, and closed positions.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cadence.api.schemas import (
    ClosedPositionListResponse,
    ClosedPositionRead,
    PaperTradeListResponse,
    PaperTradeRead,
    PaperTradingSessionListResponse,
    PaperTradingSessionRead,
    SessionRunListResponse,
    SessionRunRead,
    SessionValueHistoryResponse,
    SessionValueSnapshotRead,
)
from cadence.database import get_db
from cadence.paper_trading import service
from cadence.paper_trading.constants import SessionStatus
from cadence.paper_trading.errors import SessionNotFoundError

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/sessions", response_model=PaperTradingSessionListResponse)
def list_sessions(
    db: DbSession,
    status_filter: Annotated[
        SessionStatus | None,
        Query(alias="status", description="Filter by session status"),
    ] = None,
    limit: int = 50,
) -> PaperTradingSessionListResponse:
    """Return paper-trading sessions, most recently updated first."""
    items = [
        PaperTradingSessionRead.model_validate(row)
        for row in service.list_sessions(db, status=status_filter, limit=limit)
    ]
    total = service.count_sessions(db, status=status_filter)
    return PaperTradingSessionListResponse(items=items, total=total)


def _require_session(db: Session, session_id: uuid.UUID) -> None:
    """Raise 404 if the session does not exist."""
    try:
        service.get_session(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/sessions/{session_id}/trades", response_model=PaperTradeListResponse
)
def list_session_trades(
    session_id: uuid.UUID,
    db: DbSession,
    limit: int = 100,
) -> PaperTradeListResponse:
    """Return a session's trades, most recent first."""
    _require_session(db, session_id)
    items = [
        PaperTradeRead.model_validate(row)
        for row in service.get_session_trades(db, session_id, limit=limit)
    ]
    total = service.count_session_trades(db, session_id)
    return PaperTradeListResponse(items=items, total=total)


@router.get("/sessions/{session_id}/runs", response_model=SessionRunListResponse)
def list_session_runs(
    session_id: uuid.UUID,
    db: DbSession,
    limit: int = 50,
) -> SessionRunListResponse:
    """Return a session's run history, most recent first."""
    _require_session(db, session_id)
    items = [
        SessionRunRead.model_validate(row)
        for row in service.get_session_runs(db, session_id, limit=limit)
    ]
    total = service.count_session_runs(db, session_id)
    return SessionRunListResponse(items=items, total=total)


@router.get(
    "/sessions/{session_id}/positions",
    response_model=ClosedPositionListResponse,
)
def list_session_positions(
    session_id: uuid.UUID,
    db: DbSession,
    limit: int = 100,
) -> ClosedPositionListResponse:
    """Return a session's closed positions, most recently exited first."""
    _require_session(db, session_id)
    items = [
        ClosedPositionRead.model_validate(row)
        for row in service.get_closed_positions(db, session_id, limit=limit)
    ]
    total = service.count_closed_positions(db, session_id)
    return ClosedPositionListResponse(items=items, total=total)


@router.get(
    "/sessions/{session_id}/value-history",
    response_model=SessionValueHistoryResponse,
)
def list_session_value_history(
    session_id: uuid.UUID,
    db: DbSession,
) -> SessionValueHistoryResponse:
    """Return a session's daily value snapshots, oldest date first."""
    _require_session(db, session_id)
    items = [
        SessionValueSnapshotRead.model_validate(row)
        for row in service.list_value_snapshots(db, session_id=session_id)
    ]
    return SessionValueHistoryResponse(items=items, total=len(items))
