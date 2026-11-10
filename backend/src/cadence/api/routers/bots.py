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
    BotPresetRead,
    BotSessionCreateRequest,
    BotSessionListResponse,
    BotSessionRead,
    BotSessionSummaryRead,
    BotSnapshotResponse,
    BotStrategyCatalogEntry,
    BotTickResponse,
    BotTradeListResponse,
    BotTradeRead,
    BotValueHistoryResponse,
    BotValuePointRead,
)
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.broker import get_broker
from cadence.broker.base import Broker
from cadence.database import get_db
from cadence.notify import get_notifier
from cadence.notify.base import Notifier
from cadence.strategy_bots import presets, registry, service
from cadence.strategy_bots.constants import BotValueResolution
from cadence.strategy_bots.errors import (
    BotSessionNotArchivableError,
    BotSessionNotFoundError,
    BotSessionNotStoppedError,
    IneligibleAssetError,
    InvalidBotBenchmarkError,
    InvalidBotConfigError,
    InvalidStrategyParamsError,
    UnknownPresetError,
    UnknownStrategyError,
)
from cadence.strategy_bots.market_data import MarketData, get_market_data
from cadence.strategy_bots.models import BotSession
from cadence.strategy_bots.summary_agent import (
    BotSessionSummaryAgent,
    OpenAIBotSessionSummaryAgent,
)

router = APIRouter(prefix="/bots", tags=["bots"])


def get_bot_summary_agent() -> BotSessionSummaryAgent:
    """Provide the session-summary agent. Overridden with a fake in tests."""
    return OpenAIBotSessionSummaryAgent()


DbSession = Annotated[Session, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]
MarketDataDep = Annotated[MarketData, Depends(get_market_data)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
SummaryAgentDep = Annotated[
    BotSessionSummaryAgent, Depends(get_bot_summary_agent)
]


def _to_read(db: Session, row: BotSession) -> BotSessionRead:
    """Serialise a bot session, marking its current value from the service."""
    read = BotSessionRead.model_validate(row)
    read.current_value = service.bot_current_value(db, row)
    read.eod_value = service.bot_eod_value(db, row)
    if row.orchestrator_id is not None:
        orchestrator = db.get(BotOrchestrator, row.orchestrator_id)
        read.orchestrator_label = orchestrator.label if orchestrator else None
    return read


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


@router.get("/presets", response_model=list[BotPresetRead])
def list_presets() -> list[BotPresetRead]:
    """Return the fixed course-recipe bot presets in catalog order."""
    return [
        BotPresetRead(
            key=preset.key,
            display_name=preset.display_name,
            description=preset.description,
            course_ref=preset.course_ref,
            strategy_key=preset.strategy_key.value,
            strategy_params=dict(preset.strategy_params),
            take_profit_pct=preset.take_profit_pct,
            stop_loss_pct=preset.stop_loss_pct,
            drawdown_stop_pct=preset.drawdown_stop_pct,
            is_default=preset.is_default,
        )
        for preset in presets.list_presets()
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

    422 for an unknown strategy or preset, a strategy/preset mismatch, invalid strategy
    params, an unknown benchmark, a non-eligible / non-equity asset, an empty traded
    set, or an unknown sizing method. Preset-overridable fields absent from the request
    are passed as ``UNSET`` so the preset's value applies; an explicit ``null`` is kept.
    """
    supplied = payload.model_fields_set
    try:
        row = service.create_bot_session(
            db,
            strategy_key=payload.strategy_key,
            preset_key=payload.preset_key,
            tickers=payload.tickers,
            whole_universe=payload.whole_universe,
            initial_capital=payload.initial_capital,
            benchmark=payload.benchmark,
            strategy_params=(
                payload.strategy_params
                if "strategy_params" in supplied
                else service.UNSET
            ),
            label=payload.label,
            take_profit_pct=(
                payload.take_profit_pct
                if "take_profit_pct" in supplied
                else service.UNSET
            ),
            stop_loss_pct=(
                payload.stop_loss_pct if "stop_loss_pct" in supplied else service.UNSET
            ),
            drawdown_stop_pct=(
                payload.drawdown_stop_pct
                if "drawdown_stop_pct" in supplied
                else service.UNSET
            ),
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
        UnknownPresetError,
        InvalidStrategyParamsError,
        InvalidBotBenchmarkError,
        IneligibleAssetError,
        InvalidBotConfigError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_read(db, row)


@router.get("/sessions", response_model=BotSessionListResponse)
def list_bot_sessions(
    db: DbSession,
    include_archived: Annotated[
        bool, Query(description="Include archived sessions in the result")
    ] = False,
) -> BotSessionListResponse:
    """Return bot sessions, newest first, hiding archived ones by default."""
    rows = service.list_bot_sessions(db, include_archived=include_archived)
    items = [_to_read(db, row) for row in rows]
    return BotSessionListResponse(items=items, total=len(items))


def _get_session_or_404(db: Session, session_id: uuid.UUID) -> BotSessionRead:
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _to_read(db, row)


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
    return _to_read(db, row)


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
    return _to_read(db, row)


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
    "/sessions/{session_id}/summary", response_model=BotSessionSummaryRead
)
def get_bot_session_summary(
    session_id: uuid.UUID, db: DbSession, agent: SummaryAgentDep
) -> BotSessionSummaryRead:
    """Return a stopped session's summary: its stats + cached AI narrative.

    404 if the session is unknown, 409 if it is not stopped (no summary for an
    active session). The AI narrative is generated lazily on first view and cached;
    an agent failure returns the stats with a ``null`` narrative so a later view
    retries.
    """
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    try:
        summary = service.bot_session_summary(db, row, agent)
    except BotSessionNotStoppedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return BotSessionSummaryRead.model_validate(summary)


@router.get(
    "/sessions/{session_id}/value-history",
    response_model=BotValueHistoryResponse,
)
def list_bot_value_history(
    session_id: uuid.UUID,
    db: DbSession,
    resolution: BotValueResolution = BotValueResolution.DAILY,
) -> BotValueHistoryResponse:
    """Return a session's value history at ``resolution``, oldest first (404 if unknown).

    ``resolution`` defaults to ``daily``; ``5min``/``hourly`` read the intraday
    value points, ``daily``/``monthly`` the daily snapshot curve. An unknown
    resolution is rejected with ``422`` by enum validation.
    """
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    items = [
        BotValuePointRead.model_validate(point)
        for point in service.list_bot_value_history(db, row, resolution=resolution)
    ]
    return BotValueHistoryResponse(items=items, total=len(items), resolution=resolution)


@router.get("/sessions/{session_id}/trades", response_model=BotTradeListResponse)
def list_bot_trades(
    session_id: uuid.UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BotTradeListResponse:
    """Return one page of a session's trade ledger, most recent first (404 if unknown).

    ``total`` is the session's full trade count so the client can page; ``limit``
    defaults to 20 and is capped at 100.
    """
    try:
        row = service.get_bot_session(db, session_id)
    except BotSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    trades, total = service.list_bot_trades_page(
        db, row, limit=limit, offset=offset
    )
    items = [BotTradeRead.model_validate(trade) for trade in trades]
    return BotTradeListResponse(items=items, total=total)


@router.post("/tick", response_model=BotTickResponse)
def run_tick(
    db: DbSession,
    broker: BrokerDep,
    market_data: MarketDataDep,
    notifier: NotifierDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> BotTickResponse:
    """Flatten stopped sessions and advance every active bot session once.

    Cron-guarded and market-hours gated.
    """
    result = service.run_tick(
        db, broker=broker, market_data=market_data, notifier=notifier
    )
    # Bots the tick just finished flattening hand their cash back to the orchestrator
    # that deployed them (composed here so strategy_bots stays orchestrator-agnostic).
    orchestrator_service.settle_all_returned_capital(db)
    return BotTickResponse(
        market_open=result.market_open,
        processed=result.processed,
        skipped=result.skipped,
        flattened=result.flattened,
    )


@router.post("/snapshot-daily", response_model=BotSnapshotResponse)
def run_snapshot_daily(
    db: DbSession,
    broker: BrokerDep,
    notifier: NotifierDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> BotSnapshotResponse:
    """Record a daily value snapshot for every active session (cron-guarded)."""
    count = service.run_bot_snapshots(db, broker=broker, notifier=notifier)
    return BotSnapshotResponse(snapshots=count)
