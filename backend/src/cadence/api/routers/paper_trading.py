"""Paper-trading resource router. Mounted under ``/api/v1``.

Trade/run/position writes happen via the ai_portfolio flow; this router exposes
the session reads (listing plus a session's trades, run history, and closed
positions) and the session archive/unarchive actions.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cadence.api.schemas import (
    BenchmarkCatalogEntry,
    ClosedPositionListResponse,
    ClosedPositionRead,
    PaperTradeListResponse,
    PaperTradeRead,
    PaperTradeReconcileRead,
    PaperTradingSessionKpisRead,
    PaperTradingSessionListResponse,
    PaperTradingSessionRead,
    SessionBenchmarkChangeRequest,
    SessionRunListResponse,
    SessionRunRead,
    SessionValueHistoryResponse,
    SessionValueSnapshotRead,
)
from cadence.broker import get_broker
from cadence.broker.base import Broker
from cadence.database import get_db
from cadence.paper_trading import service
from cadence.paper_trading.constants import (
    BENCHMARK_DISPLAY_NAMES,
    Benchmark,
    SessionStatus,
)
from cadence.paper_trading.errors import (
    InvalidBenchmarkError,
    SessionNotArchivableError,
    SessionNotFoundError,
)

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])

DbSession = Annotated[Session, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]


@router.get("/sessions", response_model=PaperTradingSessionListResponse)
def list_sessions(
    db: DbSession,
    status_filter: Annotated[
        SessionStatus | None,
        Query(alias="status", description="Filter by session status"),
    ] = None,
    include_archived: Annotated[
        bool,
        Query(description="Include archived sessions in the result"),
    ] = False,
    limit: int = 50,
) -> PaperTradingSessionListResponse:
    """Return paper-trading sessions, most recently updated first."""
    items = [
        PaperTradingSessionRead.model_validate(row)
        for row in service.list_sessions(
            db,
            status=status_filter,
            include_archived=include_archived,
            limit=limit,
        )
    ]
    total = service.count_sessions(
        db, status=status_filter, include_archived=include_archived
    )
    return PaperTradingSessionListResponse(items=items, total=total)


def _require_session(db: Session, session_id: uuid.UUID) -> None:
    """Raise 404 if the session does not exist."""
    try:
        service.get_session(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/sessions/{session_id}/archive", response_model=PaperTradingSessionRead
)
def archive_session(
    session_id: uuid.UUID, db: DbSession
) -> PaperTradingSessionRead:
    """Soft-archive a stopped session (409 if it is not stopped)."""
    try:
        row = service.archive_session(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SessionNotArchivableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return PaperTradingSessionRead.model_validate(row)


@router.post(
    "/sessions/{session_id}/unarchive", response_model=PaperTradingSessionRead
)
def unarchive_session(
    session_id: uuid.UUID, db: DbSession
) -> PaperTradingSessionRead:
    """Restore an archived session to the default listing."""
    try:
        row = service.unarchive_session(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return PaperTradingSessionRead.model_validate(row)


@router.post(
    "/sessions/{session_id}/reconcile", response_model=PaperTradeReconcileRead
)
def reconcile_session(
    session_id: uuid.UUID, db: DbSession, broker: BrokerDep
) -> PaperTradeReconcileRead:
    """Reconcile a session's non-terminal orders against the broker (404 if unknown).

    Returns the reconciliation counts plus the session's refreshed trades so the
    client can render the updated statuses in one round-trip.
    """
    try:
        result = service.reconcile_session_orders(db, broker, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    trades = [
        PaperTradeRead.model_validate(row)
        for row in service.get_session_trades(db, session_id)
    ]
    return PaperTradeReconcileRead(
        trades_seen=result.trades_seen,
        trades_reconciled=result.trades_reconciled,
        trades_filled=result.trades_filled,
        trades_basis_corrected=result.trades_basis_corrected,
        trades=trades,
    )


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
    "/sessions/{session_id}/kpis",
    response_model=PaperTradingSessionKpisRead,
)
def get_session_kpis(
    session_id: uuid.UUID, db: DbSession, broker: BrokerDep
) -> PaperTradingSessionKpisRead:
    """Return a session's live performance KPIs (404 if unknown).

    Marks the session's open positions to market via the broker on each call, so
    the current value and unrealised P&L reflect current quotes rather than the
    last stored snapshot.
    """
    try:
        kpis = service.session_kpis(db, session_id=session_id, broker=broker)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return PaperTradingSessionKpisRead(
        current_value=kpis.current_value,
        realised_pnl=kpis.realised_pnl,
        unrealised_pnl=kpis.unrealised_pnl,
        total_fees=kpis.total_fees,
        total_return=kpis.total_return,
        total_return_pct=kpis.total_return_pct,
        sharpe_ratio=kpis.sharpe_ratio,
        benchmark=kpis.benchmark,
        benchmark_return_pct=kpis.benchmark_return_pct,
        excess_return_pct=kpis.excess_return_pct,
        excess_return=kpis.excess_return,
    )


@router.get(
    "/sessions/{session_id}/value-history",
    response_model=SessionValueHistoryResponse,
)
def list_session_value_history(
    session_id: uuid.UUID,
    db: DbSession,
) -> SessionValueHistoryResponse:
    """Return a session's daily value snapshots (with benchmark), oldest first."""
    _require_session(db, session_id)
    items = [
        SessionValueSnapshotRead.model_validate(point.snapshot).model_copy(
            update={"benchmark_value": point.benchmark_value}
        )
        for point in service.list_value_history(db, session_id=session_id)
    ]
    return SessionValueHistoryResponse(items=items, total=len(items))


@router.get("/benchmarks", response_model=list[BenchmarkCatalogEntry])
def list_benchmarks() -> list[BenchmarkCatalogEntry]:
    """Return the fixed benchmark catalog as ``[{id, name}]``."""
    return [
        BenchmarkCatalogEntry(id=member.value, name=BENCHMARK_DISPLAY_NAMES[member])
        for member in Benchmark
    ]


@router.put(
    "/sessions/{session_id}/benchmark",
    response_model=PaperTradingSessionRead,
)
def change_session_benchmark(
    session_id: uuid.UUID,
    payload: SessionBenchmarkChangeRequest,
    db: DbSession,
) -> PaperTradingSessionRead:
    """Switch a session's benchmark (404 unknown session, 422 invalid id)."""
    try:
        row = service.change_session_benchmark(
            db, session_id=session_id, benchmark=payload.benchmark
        )
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except InvalidBenchmarkError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PaperTradingSessionRead.model_validate(row)
