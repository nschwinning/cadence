"""AI-managed portfolio router. Mounted under ``/api/v1``.

Building a portfolio and rebalancing are both non-blocking: they queue background
work and return the event immediately (202). Clients poll the build-status
endpoint until the event reaches a terminal status. The daily-rebalance fan-out is
guarded by a shared-secret ``X-Cron-Token`` header (empty config rejects all).
"""

from __future__ import annotations

import hmac
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from cadence.ai_portfolio.agent import AIPortfolioAgent, OpenAIAIPortfolioAgent
from cadence.ai_portfolio.background import (
    AIPortfolioJobRunner,
    default_job_runner,
)
from cadence.ai_portfolio.constants import (
    AI_STRATEGY_KEY,
    EventStatus,
    EventType,
)
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    EventNotFoundError,
    SessionNotEligibleError,
)
from cadence.ai_portfolio.service import AIBuildParams
from cadence.api.routers.assets import get_market_data_provider
from cadence.api.schemas import (
    AIDailyRebalanceResponse,
    AIDailyReconcileResponse,
    AIDailySnapshotResponse,
    AIPortfolioBuildRequest,
    AIPortfolioBuildResponse,
    AIPortfolioEventRead,
    AIPortfolioRunDetail,
    AIPortfolioRunListResponse,
    AIRebalanceResponse,
    ClosedPositionRead,
    PaperTradeRead,
)
from cadence.assets.market_data import MarketDataProvider
from cadence.broker import get_broker
from cadence.broker.base import Broker
from cadence.config import settings
from cadence.database import get_db
from cadence.notify import get_notifier
from cadence.notify.base import Notifier
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import ScheduleMode, SessionStatus
from cadence.paper_trading.errors import SessionNotFoundError
from cadence.paper_trading.models import PaperTradingSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-portfolio", tags=["ai-portfolio"])


def get_ai_portfolio_agent() -> AIPortfolioAgent:
    """Provide the AI portfolio agent. Overridden with a fake in tests."""
    return OpenAIAIPortfolioAgent()


def get_ai_job_runner() -> AIPortfolioJobRunner:
    """Provide the process-wide AI job runner. Overridden in tests."""
    return default_job_runner


def require_valid_cron_token(
    x_cron_token: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request unless ``X-Cron-Token`` matches the configured secret.

    An empty configured token means no valid token exists, so every request is
    rejected — the daily rebalance must be explicitly enabled by configuring a
    non-empty ``REBALANCE_CRON_TOKEN``.
    """
    expected = settings.REBALANCE_CRON_TOKEN
    if (
        not expected
        or not x_cron_token
        or not hmac.compare_digest(x_cron_token, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing cron token"
        )


DbSession = Annotated[Session, Depends(get_db)]
Agent = Annotated[AIPortfolioAgent, Depends(get_ai_portfolio_agent)]
JobRunner = Annotated[AIPortfolioJobRunner, Depends(get_ai_job_runner)]
BrokerDep = Annotated[Broker, Depends(get_broker)]
Provider = Annotated[MarketDataProvider, Depends(get_market_data_provider)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]


@router.post(
    "/build",
    response_model=AIPortfolioBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_ai_portfolio_endpoint(
    payload: AIPortfolioBuildRequest,
    db: DbSession,
    agent: Agent,
    broker: BrokerDep,
    provider: Provider,
    job_runner: JobRunner,
) -> AIPortfolioBuildResponse:
    """Queue an AI portfolio build and return the event immediately (202)."""
    params = AIBuildParams(
        allocated_capital=payload.allocated_capital,
        risk_profile=payload.risk_profile,
        daily_rebalancing=payload.daily_rebalancing,
    )
    try:
        event = job_runner.start_build(db, params, agent, broker, provider)
    except AIPortfolioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return AIPortfolioBuildResponse(event_id=event.id, status=event.status)


@router.get("/build/status/{event_id}", response_model=AIPortfolioEventRead)
def get_build_status(
    event_id: uuid.UUID,
    db: DbSession,
    job_runner: JobRunner,
) -> AIPortfolioEventRead:
    """Return an event's current status (reaping a dead worker)."""
    try:
        event = job_runner.status(db, event_id)
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return AIPortfolioEventRead.model_validate(event)


@router.post(
    "/sessions/{session_id}/rebalance", response_model=AIRebalanceResponse
)
def rebalance_session(
    session_id: uuid.UUID,
    db: DbSession,
    agent: Agent,
    broker: BrokerDep,
    provider: Provider,
    job_runner: JobRunner,
) -> AIRebalanceResponse:
    """Trigger an AI rebalance for an eligible session.

    A rebalance already queued/running for the session is not started again — its
    in-flight event is returned with ``started=false`` instead.
    """
    try:
        _require_eligible_session(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SessionNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    event, started = job_runner.start_rebalance(
        db, session_id, agent, broker, provider
    )
    return AIRebalanceResponse(event_id=event.id, status=event.status, started=started)


@router.post(
    "/sessions/{session_id}/close", response_model=AIPortfolioRunDetail
)
def close_session_endpoint(
    session_id: uuid.UUID,
    db: DbSession,
    broker: BrokerDep,
) -> AIPortfolioRunDetail:
    """Close a session: liquidate all its open positions and stop it.

    Runs synchronously (no agent) and returns the resulting ``close`` event with
    the liquidation trades and the positions it closed — the same shape as a run
    detail, so the client can show the outcome or link straight to the run.
    """
    from cadence.ai_portfolio import service as ai_service

    try:
        event = ai_service.close_session(db, session_id, broker)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except SessionNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    trades = paper_service.get_trades_by_event(db, event.id)
    closed = paper_service.get_closed_positions_by_event(db, event.id)
    return AIPortfolioRunDetail(
        event=AIPortfolioEventRead.model_validate(event),
        trades=[PaperTradeRead.model_validate(t) for t in trades],
        closed_positions=[ClosedPositionRead.model_validate(c) for c in closed],
        rebalance_prompt_version=_resolve_prompt_version(db, event.session_id),
    )


@router.post("/rebalance-daily", response_model=AIDailyRebalanceResponse)
def rebalance_daily(
    db: DbSession,
    agent: Agent,
    broker: BrokerDep,
    provider: Provider,
    job_runner: JobRunner,
    notifier: NotifierDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> AIDailyRebalanceResponse:
    """Rebalance every active session enrolled in daily rebalancing.

    Guarded by the ``X-Cron-Token`` header. Each enrolled session's rebalance runs
    as a background job; sessions already rebalancing are skipped. A ``notifier``
    is threaded to each job so executed rebalances (and failures) are pushed —
    this is what distinguishes the daily path from the silent manual trigger.
    """
    sessions = paper_service.list_sessions(db, status=SessionStatus.ACTIVE, limit=500)
    targets = [
        s
        for s in sessions
        if s.schedule_mode == ScheduleMode.DAILY_REBALANCING.value
        and s.strategy_key == AI_STRATEGY_KEY
    ]

    triggered: list[uuid.UUID] = []
    skipped: list[uuid.UUID] = []
    for session_row in targets:
        _event, started = job_runner.start_rebalance(
            db, session_row.id, agent, broker, provider, notifier=notifier
        )
        if started:
            triggered.append(session_row.id)
        else:
            skipped.append(session_row.id)

    return AIDailyRebalanceResponse(
        sessions_triggered=len(triggered),
        session_ids=triggered,
        skipped_already_running=skipped,
    )


@router.post("/reconcile-daily", response_model=AIDailyReconcileResponse)
def reconcile_daily(
    db: DbSession,
    broker: BrokerDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> AIDailyReconcileResponse:
    """Reconcile non-terminal orders across every session against the broker.

    Guarded by the ``X-Cron-Token`` header. Runs synchronously: for each session it
    re-fetches non-terminal orders and updates their stored status/fill; one
    session's failure is logged and skipped so the batch always completes. Returns
    how many sessions were reconciled and how many trades were updated in total.
    """
    sessions = paper_service.list_sessions(db, include_archived=True, limit=500)

    sessions_reconciled = 0
    trades_reconciled = 0
    for session_row in sessions:
        try:
            result = paper_service.reconcile_session_orders(
                db, broker, session_row.id
            )
        except Exception:  # one bad session can't abort the batch
            logger.warning(
                "reconcile-daily: session %s failed", session_row.id, exc_info=True
            )
            continue
        sessions_reconciled += 1
        trades_reconciled += result.trades_reconciled

    return AIDailyReconcileResponse(
        sessions_reconciled=sessions_reconciled,
        trades_reconciled=trades_reconciled,
    )


@router.post("/snapshot-daily", response_model=AIDailySnapshotResponse)
def snapshot_daily(
    db: DbSession,
    broker: BrokerDep,
    notifier: NotifierDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> AIDailySnapshotResponse:
    """Record an end-of-day value snapshot for every active AI session.

    Guarded by the ``X-Cron-Token`` header. Runs synchronously: it marks each
    session's holdings to market, upserts one snapshot per session for today, and
    sends a single daily P&L report via the ``notifier`` (best-effort). Returns how
    many sessions were snapshotted.
    """
    from cadence.ai_portfolio import service as ai_service

    session_ids = ai_service.snapshot_all_sessions(
        db, broker=broker, notifier=notifier
    )
    return AIDailySnapshotResponse(
        sessions_snapshotted=len(session_ids), session_ids=session_ids
    )


@router.get(
    "/sessions/{session_id}/events",
    response_model=list[AIPortfolioEventRead],
)
def list_session_events(
    session_id: uuid.UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AIPortfolioEventRead]:
    """Return a session's AI events (build + rebalances), newest first."""
    from cadence.ai_portfolio import service as ai_service

    return [
        AIPortfolioEventRead.model_validate(event)
        for event in ai_service.list_session_events(db, session_id, limit=limit)
    ]


@router.get("/runs", response_model=AIPortfolioRunListResponse)
def list_ai_runs_endpoint(
    db: DbSession,
    event_type: Annotated[EventType | None, Query()] = None,
    run_status: Annotated[EventStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AIPortfolioRunListResponse:
    """List AI runs across all sessions, newest first (the Runs history page)."""
    from cadence.ai_portfolio import service as ai_service

    events = ai_service.list_ai_runs(
        db,
        event_type=event_type,
        status=run_status,
        limit=limit,
        offset=offset,
    )
    total = ai_service.count_ai_runs(db, event_type=event_type, status=run_status)
    return AIPortfolioRunListResponse(
        items=[AIPortfolioEventRead.model_validate(e) for e in events],
        total=total,
    )


@router.get("/runs/{event_id}", response_model=AIPortfolioRunDetail)
def get_ai_run_detail(
    event_id: uuid.UUID,
    db: DbSession,
) -> AIPortfolioRunDetail:
    """Return one AI run with the trades it opened and the positions it closed."""
    from cadence.ai_portfolio import service as ai_service

    try:
        event = ai_service.get_event(db, event_id)
    except EventNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    trades = paper_service.get_trades_by_event(db, event_id)
    closed = paper_service.get_closed_positions_by_event(db, event_id)
    return AIPortfolioRunDetail(
        event=AIPortfolioEventRead.model_validate(event),
        trades=[PaperTradeRead.model_validate(t) for t in trades],
        closed_positions=[ClosedPositionRead.model_validate(c) for c in closed],
        rebalance_prompt_version=_resolve_prompt_version(db, event.session_id),
    )


def _resolve_prompt_version(
    db: Session, session_id: uuid.UUID | None
) -> int | None:
    """The rebalance-prompt version frozen on the run's session, or None if it has none."""
    if session_id is None:
        return None
    try:
        return paper_service.get_session(db, session_id).rebalance_prompt_version
    except SessionNotFoundError:
        return None


def _require_eligible_session(db: Session, session_id: uuid.UUID) -> None:
    """Raise if the session is missing or not an active AI-managed session."""
    session_row: PaperTradingSession = paper_service.get_session(db, session_id)
    if session_row.strategy_key != AI_STRATEGY_KEY:
        raise SessionNotEligibleError("only AI-managed sessions can be rebalanced")
    if session_row.status != SessionStatus.ACTIVE.value:
        raise SessionNotEligibleError(
            f"session is {session_row.status}, not active"
        )
