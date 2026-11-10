"""HTTP API for bot orchestrators: lifecycle, decision runs, and the cron trigger.

Thin layer over :mod:`cadence.bot_orchestrator`. Runs execute in the background: the
endpoint queues a run, commits it, then hands its id to the single-worker runner, so a
client polls the orchestrator (or run) until the run is terminal.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.api.cron_auth import require_valid_cron_token
from cadence.api.schemas import (
    BotOrchestratorCreateRequest,
    BotOrchestratorDetailRead,
    BotOrchestratorListResponse,
    BotOrchestratorRead,
    OrchestratorBotRead,
    OrchestratorRunDueResponse,
    OrchestratorRunListResponse,
    OrchestratorRunRead,
    OrchestratorRunSummaryRead,
)
from cadence.bot_orchestrator import costs, runs, service
from cadence.bot_orchestrator.background import (
    OrchestratorJobRunner,
    get_orchestrator_job_runner,
)
from cadence.bot_orchestrator.constants import OrchestratorTrigger
from cadence.bot_orchestrator.errors import (
    InvalidOrchestratorConfigError,
    OrchestratorNotActiveError,
    OrchestratorNotArchivableError,
    OrchestratorNotFoundError,
    OrchestratorRunInProgressError,
    OrchestratorRunNotFoundError,
)
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorRun
from cadence.database import get_db
from cadence.notify import get_notifier
from cadence.notify.base import Notifier
from cadence.strategy_bots import presets
from cadence.strategy_bots.errors import UnknownPresetError
from cadence.strategy_bots.models import BotSession

router = APIRouter(prefix="/bot-orchestrators", tags=["bot-orchestrators"])

DbSession = Annotated[Session, Depends(get_db)]
RunnerDep = Annotated[OrchestratorJobRunner, Depends(get_orchestrator_job_runner)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]

_RUNS_PAGE_DEFAULT = 10
_RUNS_PAGE_MAX = 100


# Serialisation -----------------------------------------------------------------
def _run_summary(
    run: BotOrchestratorRun, run_costs: dict[uuid.UUID, float] | None = None
) -> OrchestratorRunSummaryRead:
    decision = run.decision or {}
    return OrchestratorRunSummaryRead(
        usage=run.usage,
        ai_cost_usd=run_costs.get(run.id) if run_costs is not None else None,
        id=run.id,
        trigger=run.trigger,
        status=run.status,
        model=run.model,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        error=run.error,
        market_summary=decision.get("market_summary"),
        applied=run.applied or [],
        rejected=run.rejected or [],
    )


def _run_read(run: BotOrchestratorRun) -> OrchestratorRunRead:
    return OrchestratorRunRead(
        **_run_summary(run, costs.run_ai_costs([run])).model_dump(),
        orchestrator_id=run.orchestrator_id,
        prompt_version=run.prompt_version,
        briefing=run.briefing,
        decision=run.decision,
        research=run.research or [],
    )


def _preset_name(key: str | None) -> str | None:
    if key is None:
        return None
    try:
        return presets.get_preset(key).display_name
    except UnknownPresetError:
        return key


def _bot_read(db: Session, bot: BotSession) -> OrchestratorBotRead:
    value = service.bot_value(db, bot)
    return OrchestratorBotRead(
        id=bot.id,
        label=bot.label,
        preset_key=bot.preset_key,
        preset_name=_preset_name(bot.preset_key),
        strategy_key=bot.strategy_key,
        tickers=[s.ticker for s in bot.symbols],
        status=bot.status,
        stop_reason=bot.stop_reason,
        initial_capital=bot.initial_capital,
        current_value=value,
        total_return_pct=(value - bot.initial_capital) / bot.initial_capital,
        open_positions=len(bot.positions),
        created_at=bot.created_at,
        stopped_at=bot.stopped_at,
        capital_returned_at=bot.capital_returned_at,
    )


def _latest_run(db: Session, orchestrator: BotOrchestrator) -> BotOrchestratorRun | None:
    return (
        db.execute(
            select(BotOrchestratorRun)
            .where(BotOrchestratorRun.orchestrator_id == orchestrator.id)
            .order_by(BotOrchestratorRun.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _read(
    db: Session,
    orchestrator: BotOrchestrator,
    *,
    ai_cost: float | None,
    latest: BotOrchestratorRun | None,
    run_costs: dict[uuid.UUID, float] | None,
) -> BotOrchestratorRead:
    figures = service.orchestrator_figures(db, orchestrator)
    return BotOrchestratorRead(
        ai_cost_usd=ai_cost,
        id=orchestrator.id,
        label=orchestrator.label,
        status=orchestrator.status,
        capital=orchestrator.capital,
        free_capital=orchestrator.free_capital,
        allocated_capital=figures.allocated_capital,
        value=figures.value,
        total_return_pct=figures.total_return_pct,
        max_parallel_bots=orchestrator.max_parallel_bots,
        max_bot_share=orchestrator.max_bot_share,
        max_tickers_per_bot=orchestrator.max_tickers_per_bot,
        cadence=orchestrator.cadence,
        model=orchestrator.model,
        benchmark=orchestrator.benchmark,
        active_bots=figures.active_bots,
        liquidating_bots=figures.liquidating_bots,
        created_at=orchestrator.created_at,
        stopped_at=orchestrator.stopped_at,
        archived_at=orchestrator.archived_at,
        last_run=_run_summary(latest, run_costs) if latest is not None else None,
    )


def _reads(
    db: Session, orchestrators: list[BotOrchestrator]
) -> list[BotOrchestratorRead]:
    """Serialise orchestrators with their AI costs (two batched cost queries)."""
    totals = costs.orchestrator_ai_costs(db, orchestrators)
    latest = {o.id: _latest_run(db, o) for o in orchestrators}
    run_costs = costs.run_ai_costs([r for r in latest.values() if r is not None])
    return [
        _read(
            db,
            o,
            ai_cost=totals.get(o.id) if totals is not None else None,
            latest=latest[o.id],
            run_costs=run_costs,
        )
        for o in orchestrators
    ]


def _detail(db: Session, orchestrator: BotOrchestrator) -> BotOrchestratorDetailRead:
    return BotOrchestratorDetailRead(
        **_reads(db, [orchestrator])[0].model_dump(),
        bots=[_bot_read(db, b) for b in service.orchestrator_bots(db, orchestrator)],
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _load(db: Session, orchestrator_id: uuid.UUID) -> BotOrchestrator:
    try:
        return service.get_orchestrator(db, orchestrator_id)
    except OrchestratorNotFoundError as exc:
        raise _not_found(exc) from exc


# Lifecycle ---------------------------------------------------------------------
@router.get("", response_model=BotOrchestratorListResponse)
def list_orchestrators(
    db: DbSession, include_archived: bool = False
) -> BotOrchestratorListResponse:
    """Orchestrators newest first (archived only when requested)."""
    rows = service.list_orchestrators(db, include_archived=include_archived)
    return BotOrchestratorListResponse(items=_reads(db, rows), total=len(rows))


@router.post(
    "", response_model=BotOrchestratorDetailRead, status_code=status.HTTP_201_CREATED
)
def create_orchestrator(
    payload: BotOrchestratorCreateRequest, db: DbSession
) -> BotOrchestratorDetailRead:
    """Deploy an orchestrator (no AI call, no bots yet). 422 on invalid config."""
    try:
        orchestrator = service.create_orchestrator(
            db,
            label=payload.label,
            capital=payload.capital,
            max_parallel_bots=payload.max_parallel_bots,
            max_bot_share=payload.max_bot_share,
            max_tickers_per_bot=payload.max_tickers_per_bot,
            cadence=payload.cadence,
            model=payload.model,
            benchmark=payload.benchmark,
        )
    except InvalidOrchestratorConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _detail(db, orchestrator)


@router.get("/{orchestrator_id}", response_model=BotOrchestratorDetailRead)
def get_orchestrator(
    orchestrator_id: uuid.UUID, db: DbSession
) -> BotOrchestratorDetailRead:
    """One orchestrator with its capital figures, bots and latest run. 404 if unknown."""
    return _detail(db, _load(db, orchestrator_id))


@router.post("/{orchestrator_id}/stop", response_model=BotOrchestratorDetailRead)
def stop_orchestrator(
    orchestrator_id: uuid.UUID, db: DbSession
) -> BotOrchestratorDetailRead:
    """Stop the orchestrator and every active bot it deployed (idempotent)."""
    try:
        orchestrator = service.stop_orchestrator(db, orchestrator_id)
    except OrchestratorNotFoundError as exc:
        raise _not_found(exc) from exc
    return _detail(db, orchestrator)


@router.post("/{orchestrator_id}/archive", response_model=BotOrchestratorDetailRead)
def archive_orchestrator(
    orchestrator_id: uuid.UUID, db: DbSession
) -> BotOrchestratorDetailRead:
    """Archive a stopped orchestrator. 409 while it is still active."""
    try:
        orchestrator = service.archive_orchestrator(db, orchestrator_id)
    except OrchestratorNotFoundError as exc:
        raise _not_found(exc) from exc
    except OrchestratorNotArchivableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return _detail(db, orchestrator)


# Runs --------------------------------------------------------------------------
@router.post("/run-due", response_model=OrchestratorRunDueResponse)
def run_due(
    db: DbSession,
    runner: RunnerDep,
    notifier: NotifierDep,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> OrchestratorRunDueResponse:
    """Queue and start a scheduled run for every due orchestrator (cron-guarded)."""
    result = runs.queue_due_runs(db, now=datetime.now(UTC))
    db.commit()
    for run in result.queued:
        runner.submit(run.id, notifier)
    return OrchestratorRunDueResponse(
        started=len(result.queued),
        not_due=result.not_due,
        already_running=result.already_running,
    )


@router.get("/runs/{run_id}", response_model=OrchestratorRunRead)
def get_run(run_id: uuid.UUID, db: DbSession) -> OrchestratorRunRead:
    """A decision run in full. 404 if unknown."""
    try:
        return _run_read(runs.get_run(db, run_id))
    except OrchestratorRunNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/{orchestrator_id}/runs",
    response_model=OrchestratorRunSummaryRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_run(
    orchestrator_id: uuid.UUID, db: DbSession, runner: RunnerDep
) -> OrchestratorRunSummaryRead:
    """Queue a manual run now. 409 if not active or a run is already in progress."""
    orchestrator = _load(db, orchestrator_id)
    try:
        run = runs.queue_run(db, orchestrator, OrchestratorTrigger.MANUAL)
    except (OrchestratorNotActiveError, OrchestratorRunInProgressError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.commit()
    runner.submit(run.id)
    return _run_summary(run)


@router.get("/{orchestrator_id}/runs", response_model=OrchestratorRunListResponse)
def list_runs(
    orchestrator_id: uuid.UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=_RUNS_PAGE_MAX)] = _RUNS_PAGE_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrchestratorRunListResponse:
    """A page of the orchestrator's runs, newest first."""
    orchestrator = _load(db, orchestrator_id)
    rows, total = runs.list_runs(db, orchestrator, limit=limit, offset=offset)
    run_costs = costs.run_ai_costs(rows)
    return OrchestratorRunListResponse(
        items=[_run_summary(row, run_costs) for row in rows], total=total
    )
