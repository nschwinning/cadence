"""Strategy-bot resource router. Mounted under ``/api/v1``.

Exposes the bot-session lifecycle (create / list / detail / stop / archive), the
per-session performance reads (KPIs, value history, trade ledger), the strategy
catalog, and the two cron-guarded jobs — the stateless-recompute ``/tick`` and the
daily value ``/snapshot-daily`` — both guarded by the shared ``X-Cron-Token`` header
(empty config rejects all), reusing :func:`require_valid_cron_token`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cadence.api.cron_auth import require_valid_cron_token
from cadence.api.schemas import (
    BotKpisRead,
    BotSessionCreateRequest,
    BotSessionListResponse,
    BotSessionRead,
    BotSnapshotResponse,
    BotStrategyCatalogEntry,
    BotTickResponse,
    BotTradeListResponse,
    BotTradeRead,
    BotValueHistoryResponse,
    BotValueSnapshotRead,
)
from cadence.broker import get_broker
from cadence.broker.base import Broker
from cadence.database import get_db
from cadence.strategy_bots import registry, service
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotFoundError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
    InvalidStrategyParamsError,
    UnknownStrategyError,
)
from cadence.strategy_bots.market_data import MarketData, get_market_data

router = APIRouter(prefix="/bots", tags=["bots"])

DbSession = Annotated[Session, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]
MarketDataDep = Annotated[MarketData, Depends(get_market_data)]


@router.get("/strategies", response_model=list[BotStrategyCatalogEntry])
def list_strategies() -> list[BotStrategyCatalogEntry]:
    """Return the registered bot strategies with their default param schema."""
    return [
        BotStrategyCatalogEntry(
            key=registration.key.value,
            display_name=registration.display_name,
            explanation=registration.explanation,
            required_history=registration.params_schema().required_history,
            params_schema=registration.params_schema.model_json_schema(),
        )
        for registration in registry.list_strategies()
    ]


@router.post(
    "/sessions",
    response_model=BotSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bot_session(
    payload: BotSessionCreateRequest, db: DbSession
) -> BotSessionRead:
    """Create an active bot session over a set of eligible universe equities.

    422 for an unknown strategy, invalid strategy params, an unknown benchmark, a
    non-eligible / non-equity asset, an empty traded set, or an unknown sizing method.
    """
    try:
        row = service.create_bot_session(
            db,
            strategy_key=payload.strategy_key,
            tickers=payload.tickers,
            whole_universe=payload.whole_universe,
            initial_capital=payload.initial_capital,
            benchmark=payload.benchmark,
            strategy_params=payload.strategy_params,
            label=payload.label,
            take_profit_pct=payload.take_profit_pct,
            stop_loss_pct=payload.stop_loss_pct,
            drawdown_stop_pct=payload.drawdown_stop_pct,
            cash_buffer_pct=payload.cash_buffer_pct,
            sizing_method=payload.sizing_method,
            risk_pct=payload.risk_pct,
            atr_period=payload.atr_period,
            atr_k=payload.atr_k,
            max_position_pct=payload.max_position_pct,
            max_positions=payload.max_positions,
        )
    except (
        UnknownStrategyError,
        InvalidStrategyParamsError,
        InvalidBotBenchmarkError,
        IneligibleAssetError,
        InvalidBotConfigError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return BotSessionRead.model_validate(row)


@router.get("/sessions", response_model=BotSessionListResponse)
def list_bot_sessions(
    db: DbSession,
    include_archived: Annotated[
        bool, Query(description="Include archived sessions in the result")
    ] = False,
) -> BotSessionListResponse:
    """Return bot sessions, newest first, hiding archived ones by default."""
    rows = service.list_bot_sessions(db, include_archived=include_archived)
    items = [BotSessionRead.model_validate(row) for row in rows]
    return BotSessionListResponse(items=items, total=len(items))


def _get_session_or_404(db: Session, session_id: uuid.UUID) -> BotSessionRead:
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return BotSessionRead.model_validate(row)


@router.get("/sessions/{session_id}", response_model=BotSessionRead)
def get_bot_session(session_id: uuid.UUID, db: DbSession) -> BotSessionRead:
    """Return a single bot session (404 if unknown)."""
    return _get_session_or_404(db, session_id)


@router.post("/sessions/{session_id}/stop", response_model=BotSessionRead)
def stop_bot_session(session_id: uuid.UUID, db: DbSession) -> BotSessionRead:
    """Stop an active session so it is no longer ticked (404 if unknown)."""
    try:
        row = service.stop_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return BotSessionRead.model_validate(row)


@router.post("/sessions/{session_id}/archive", response_model=BotSessionRead)
def archive_bot_session(session_id: uuid.UUID, db: DbSession) -> BotSessionRead:
    """Archive a stopped session (404 unknown, 409 if it is not stopped)."""
    try:
        row = service.archive_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BotSessionNotArchivableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return BotSessionRead.model_validate(row)


@router.get("/sessions/{session_id}/kpis", response_model=BotKpisRead)
def get_bot_session_kpis(session_id: uuid.UUID, db: DbSession) -> BotKpisRead:
    """Return a session's KPIs from its own ledger + snapshots (404 if unknown)."""
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return BotKpisRead.model_validate(service.bot_session_kpis(db, row))


@router.get(
    "/sessions/{session_id}/value-history",
    response_model=BotValueHistoryResponse,
)
def list_bot_value_history(
    session_id: uuid.UUID, db: DbSession
) -> BotValueHistoryResponse:
    """Return a session's daily value snapshots, oldest first (404 if unknown)."""
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    items = [
        BotValueSnapshotRead.model_validate(snap)
        for snap in service.list_bot_snapshots(db, row)
    ]
    return BotValueHistoryResponse(items=items, total=len(items))


@router.get("/sessions/{session_id}/trades", response_model=BotTradeListResponse)
def list_bot_trades(
    session_id: uuid.UUID, db: DbSession
) -> BotTradeListResponse:
    """Return a session's trade ledger, most recent first (404 if unknown)."""
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    trades = sorted(row.trades, key=lambda t: t.created_at, reverse=True)
    items = [BotTradeRead.model_validate(trade) for trade in trades]
    return BotTradeListResponse(items=items, total=len(items))


@router.post("/tick", response_model=BotTickResponse)
def run_tick(
    db: DbSession,
    broker: BrokerDep,
    market_data: MarketDataDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> BotTickResponse:
    """Advance every active bot session once (cron-guarded, market-hours gated)."""
    result = service.run_tick(db, broker=broker, market_data=market_data)
    return BotTickResponse(
        market_open=result.market_open,
        processed=result.processed,
        skipped=result.skipped,
    )


@router.post("/snapshot-daily", response_model=BotSnapshotResponse)
def run_snapshot_daily(
    db: DbSession,
    broker: BrokerDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> BotSnapshotResponse:
    """Record a daily value snapshot for every active session (cron-guarded)."""
    count = service.run_bot_snapshots(db, broker=broker)
    return BotSnapshotResponse(snapshots=count)
