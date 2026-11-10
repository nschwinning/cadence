"""Decision runs: due-ness, queueing, validation, and execution.

A run builds the briefing, asks the agent for a decision, then validates and applies it
deterministically: stops first, then deploys in the order given, every action checked
against the catalog, the eligible universe and the orchestrator's limits. Rejected
actions are recorded with a reason and never block the others. The apply step runs in a
savepoint so an unexpected error leaves nothing half-applied.

Runs place no orders themselves: stopped bots are sold, and deployed bots start
trading, at the next intraday tick while the market is open. A run is skipped on
non-trading days (weekends and market holidays).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence.agents import llm_trace
from cadence.agents.tools import record_web_searches
from cadence.ai_portfolio.scheduling import MARKET_TIMEZONE, rebalance_due
from cadence.bot_orchestrator import service
from cadence.bot_orchestrator.agent import (
    ORCHESTRATOR_PROMPT_VERSION,
    DeployAction,
    OrchestratorAgent,
    OrchestratorDecision,
    StopAction,
)
from cadence.bot_orchestrator.briefing import SentimentResolver, build_briefing
from cadence.bot_orchestrator.constants import (
    COUNTING_RUN_STATUSES,
    LIVE_RUN_STATUSES,
    MIN_BOT_CAPITAL,
    OrchestratorRunStatus,
    OrchestratorStatus,
    OrchestratorTrigger,
)
from cadence.bot_orchestrator.errors import (
    OrchestratorNotActiveError,
    OrchestratorRunInProgressError,
    OrchestratorRunNotFoundError,
    OrchestratorUnavailableError,
)
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorRun
from cadence.broker.base import Broker, BrokerError
from cadence.news_sentiment.service import resolve_sentiment_annotations
from cadence.notify.base import Notifier
from cadence.paper_trading.constants import cadence_to_schedule_mode
from cadence.strategy_bots import presets
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin, BotSessionStatus, StopReason
from cadence.strategy_bots.errors import StrategyBotError, UnknownPresetError

logger = logging.getLogger(__name__)

#: Tolerance when comparing a deploy's capital with a limit (float noise from the AI).
_CAPITAL_EPSILON = 1e-6


# Validation ------------------------------------------------------------------
@dataclass
class DecisionState:
    """The limits and catalog a decision is validated against (mutated as it goes)."""

    active_bot_ids: set[str]
    eligible_tickers: set[str]
    preset_keys: set[str]
    free_capital: float
    open_slots: int
    max_bot_capital: float
    max_tickers_per_bot: int


@dataclass
class ValidatedDecision:
    """The accepted stops and deploys (tickers normalised) and every rejection."""

    stops: list[StopAction] = field(default_factory=list)
    deploys: list[DeployAction] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


def _reject(
    result: ValidatedDecision, kind: str, action: StopAction | DeployAction, reason: str
) -> None:
    result.rejected.append({"kind": kind, "action": action.model_dump(), "reason": reason})


def _deploy_rejection(action: DeployAction, state: DecisionState) -> str | None:
    """The reason a deploy must be rejected under ``state``, or ``None``."""
    if action.preset_key not in state.preset_keys:
        return f"unknown preset {action.preset_key!r}"
    tickers = [t.strip().upper() for t in action.tickers]
    if not tickers:
        return "no tickers given"
    if len(set(tickers)) != len(tickers):
        return "duplicate tickers"
    if len(tickers) > state.max_tickers_per_bot:
        return (
            f"{len(tickers)} tickers exceed the per-bot limit of "
            f"{state.max_tickers_per_bot}"
        )
    ineligible = [t for t in tickers if t not in state.eligible_tickers]
    if ineligible:
        return f"not eligible universe equities: {', '.join(ineligible)}"
    if action.capital < MIN_BOT_CAPITAL - _CAPITAL_EPSILON:
        return f"capital {action.capital:,.2f} is below the {MIN_BOT_CAPITAL:,.0f} minimum"
    if action.capital > state.max_bot_capital + _CAPITAL_EPSILON:
        return (
            f"capital {action.capital:,.2f} exceeds the per-bot maximum of "
            f"{state.max_bot_capital:,.2f}"
        )
    if action.capital > state.free_capital + _CAPITAL_EPSILON:
        return (
            f"capital {action.capital:,.2f} exceeds the free capital of "
            f"{state.free_capital:,.2f}"
        )
    if state.open_slots < 1:
        return "no bot slot left (parallel-bot limit reached)"
    return None


def validate_decision(
    decision: OrchestratorDecision, state: DecisionState
) -> ValidatedDecision:
    """Validate stops then deploys against ``state`` (a mutable copy of the limits).

    A stop frees its slot for later deploys in the same decision; its cash does not
    return until the bot is flat, so it never funds a same-run deploy.
    """
    result = ValidatedDecision()
    stopped: set[str] = set()
    for stop in decision.stops:
        if stop.bot_id not in state.active_bot_ids or stop.bot_id in stopped:
            _reject(result, "stop", stop, "not an active bot of this orchestrator")
            continue
        stopped.add(stop.bot_id)
        state.open_slots += 1
        result.stops.append(stop)
    for deploy in decision.deploys:
        reason = _deploy_rejection(deploy, state)
        if reason is not None:
            _reject(result, "deploy", deploy, reason)
            continue
        normalised = deploy.model_copy(
            update={"tickers": [t.strip().upper() for t in deploy.tickers]}
        )
        state.free_capital -= deploy.capital
        state.open_slots -= 1
        result.deploys.append(normalised)
    return result


def decision_state(db: Session, orchestrator: BotOrchestrator) -> DecisionState:
    """Build the validation state from the orchestrator's current bots and limits."""
    figures = service.orchestrator_figures(db, orchestrator)
    active_ids = {
        str(bot.id)
        for bot in service.orchestrator_bots(db, orchestrator)
        if bot.status == BotSessionStatus.ACTIVE.value
    }
    return DecisionState(
        active_bot_ids=active_ids,
        eligible_tickers={
            asset.ticker.upper() for asset in bot_service.resolve_universe_equities(db)
        },
        preset_keys={p.key for p in presets.list_presets()},
        free_capital=orchestrator.free_capital,
        open_slots=max(orchestrator.max_parallel_bots - len(active_ids), 0),
        max_bot_capital=orchestrator.max_bot_share * figures.value,
        max_tickers_per_bot=orchestrator.max_tickers_per_bot,
    )


# Due-ness & queueing ---------------------------------------------------------
def last_counting_run_at(db: Session, orchestrator: BotOrchestrator) -> datetime | None:
    """When the newest succeeded-or-partial run finished (the cadence anchor)."""
    stmt = select(func.max(BotOrchestratorRun.finished_at)).where(
        BotOrchestratorRun.orchestrator_id == orchestrator.id,
        BotOrchestratorRun.status.in_([s.value for s in COUNTING_RUN_STATUSES]),
    )
    return db.execute(stmt).scalar_one_or_none()


def orchestrator_due(db: Session, orchestrator: BotOrchestrator, now: datetime) -> bool:
    """Whether the orchestrator is due under the AI-portfolio cadence rules."""
    mode = cadence_to_schedule_mode(orchestrator.cadence)
    return rebalance_due(mode.value, last_counting_run_at(db, orchestrator), now)


def live_run(db: Session, orchestrator: BotOrchestrator) -> BotOrchestratorRun | None:
    """The orchestrator's queued-or-running run, if any."""
    stmt = select(BotOrchestratorRun).where(
        BotOrchestratorRun.orchestrator_id == orchestrator.id,
        BotOrchestratorRun.status.in_([s.value for s in LIVE_RUN_STATUSES]),
    )
    return db.execute(stmt).scalars().first()


def queue_run(
    db: Session, orchestrator: BotOrchestrator, trigger: OrchestratorTrigger
) -> BotOrchestratorRun:
    """Create a queued run, or raise if the orchestrator is inactive or busy."""
    if orchestrator.status != OrchestratorStatus.ACTIVE.value:
        raise OrchestratorNotActiveError("the orchestrator is not active")
    if live_run(db, orchestrator) is not None:
        raise OrchestratorRunInProgressError("a run is already queued or running")
    run = BotOrchestratorRun(
        orchestrator_id=orchestrator.id,
        trigger=trigger.value,
        status=OrchestratorRunStatus.QUEUED.value,
        model=orchestrator.model,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError as exc:  # lost a race with a concurrent queue_run
        raise OrchestratorRunInProgressError(
            "a run is already queued or running"
        ) from exc
    return run


@dataclass(frozen=True)
class DueRunsResult:
    """Outcome of one scheduled trigger."""

    queued: list[BotOrchestratorRun]
    not_due: int
    already_running: int


def queue_due_runs(db: Session, *, now: datetime) -> DueRunsResult:
    """Queue a scheduled run for every active orchestrator that is due."""
    queued: list[BotOrchestratorRun] = []
    not_due = 0
    running = 0
    for orchestrator in service.active_orchestrators(db):
        if live_run(db, orchestrator) is not None:
            running += 1
        elif not orchestrator_due(db, orchestrator, now):
            not_due += 1
        else:
            queued.append(queue_run(db, orchestrator, OrchestratorTrigger.SCHEDULED))
    return DueRunsResult(queued=queued, not_due=not_due, already_running=running)


def get_run(db: Session, run_id: uuid.UUID) -> BotOrchestratorRun:
    """Load a run by id, or raise ``OrchestratorRunNotFoundError``."""
    run = db.get(BotOrchestratorRun, run_id)
    if run is None:
        raise OrchestratorRunNotFoundError(str(run_id))
    return run


def list_runs(
    db: Session, orchestrator: BotOrchestrator, *, limit: int, offset: int
) -> tuple[list[BotOrchestratorRun], int]:
    """A page of the orchestrator's runs, newest first, plus the total."""
    base = BotOrchestratorRun.orchestrator_id == orchestrator.id
    total = db.execute(
        select(func.count()).select_from(BotOrchestratorRun).where(base)
    ).scalar_one()
    rows = db.execute(
        select(BotOrchestratorRun)
        .where(base)
        .order_by(BotOrchestratorRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), int(total)


def fail_orphaned_runs(db: Session) -> int:
    """Fail every queued-or-running run (called at startup after a restart)."""
    orphans = list(
        db.execute(
            select(BotOrchestratorRun).where(
                BotOrchestratorRun.status.in_([s.value for s in LIVE_RUN_STATUSES])
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    for run in orphans:
        run.status = OrchestratorRunStatus.FAILED.value
        run.error = "interrupted by a restart"
        run.finished_at = now
    if orphans:
        db.commit()
    return len(orphans)


# Execution -------------------------------------------------------------------
def _finish(
    db: Session,
    run: BotOrchestratorRun,
    status: OrchestratorRunStatus,
    *,
    started: float,
    error: str | None = None,
) -> None:
    run.status = status.value
    run.error = error
    run.finished_at = datetime.now(UTC)
    run.duration_ms = int((time.monotonic() - started) * 1000)
    db.commit()


def _apply(
    db: Session,
    orchestrator: BotOrchestrator,
    validated: ValidatedDecision,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply accepted stops then deploys; deploy domain errors become rejections."""
    applied: list[dict[str, Any]] = []
    rejected = list(validated.rejected)
    for stop in validated.stops:
        bot = bot_service.stop_bot_session(
            db, uuid.UUID(stop.bot_id), reason=StopReason.ORCHESTRATOR
        )
        applied.append(
            {
                "kind": "stop",
                "bot_id": stop.bot_id,
                "preset_key": bot.preset_key,
                "tickers": [s.ticker for s in bot.symbols],
                "reason": stop.reason,
            }
        )
    for deploy in validated.deploys:
        try:
            with db.begin_nested():
                bot = bot_service.create_bot_session(
                    db,
                    preset_key=deploy.preset_key,
                    tickers=deploy.tickers,
                    initial_capital=deploy.capital,
                    benchmark=orchestrator.benchmark,
                    origin=BotOrigin.ORCHESTRATOR,
                    orchestrator_id=orchestrator.id,
                )
        except StrategyBotError as exc:
            _reject_into(rejected, deploy, f"could not create the bot: {exc}")
            continue
        orchestrator.free_capital -= deploy.capital
        applied.append(
            {
                "kind": "deploy",
                "bot_id": str(bot.id),
                "preset_key": deploy.preset_key,
                "tickers": deploy.tickers,
                "capital": deploy.capital,
                "rationale": deploy.rationale,
            }
        )
    # Stopped bots that were already flat hand their cash back right away.
    service.settle_returned_capital(db, orchestrator)
    return applied, rejected


def _reject_into(rejected: list[dict[str, Any]], deploy: DeployAction, reason: str) -> None:
    rejected.append({"kind": "deploy", "action": deploy.model_dump(), "reason": reason})


def _outcome(
    decision: OrchestratorDecision,
    applied: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> tuple[OrchestratorRunStatus, str | None]:
    if not decision.stops and not decision.deploys:
        return OrchestratorRunStatus.SUCCEEDED, None
    if applied and rejected:
        return OrchestratorRunStatus.PARTIAL, None
    if applied:
        return OrchestratorRunStatus.SUCCEEDED, None
    return OrchestratorRunStatus.FAILED, "every action in the decision was rejected"


def execute_run(
    db: Session,
    run_id: uuid.UUID,
    *,
    agent: OrchestratorAgent,
    broker: Broker,
    notifier: Notifier | None = None,
    now: datetime | None = None,
    resolve_sentiment: SentimentResolver = resolve_sentiment_annotations,
) -> BotOrchestratorRun:
    """Execute one queued run end to end and record its outcome. Never raises."""
    run = get_run(db, run_id)
    orchestrator = service.get_orchestrator(db, run.orchestrator_id)
    started = time.monotonic()
    run_now = now or datetime.now(UTC)
    run.status = OrchestratorRunStatus.RUNNING.value
    run.started_at = datetime.now(UTC)
    run.prompt_version = ORCHESTRATOR_PROMPT_VERSION
    db.commit()

    if orchestrator.status != OrchestratorStatus.ACTIVE.value:
        _finish(
            db,
            run,
            OrchestratorRunStatus.SKIPPED,
            started=started,
            error="the orchestrator is not active",
        )
        return run
    try:
        trading_day = broker.is_trading_day(run_now.astimezone(MARKET_TIMEZONE).date())
    except BrokerError as exc:
        _finish(
            db,
            run,
            OrchestratorRunStatus.FAILED,
            started=started,
            error=f"market calendar unavailable: {exc}",
        )
        _notify_failure(notifier, run, orchestrator)
        return run
    if not trading_day:
        _finish(
            db,
            run,
            OrchestratorRunStatus.SKIPPED,
            started=started,
            error="not a trading day",
        )
        return run

    research: list[dict[str, Any]] = []
    try:
        service.settle_returned_capital(db, orchestrator)
        briefing = build_briefing(
            db, orchestrator, now=run_now, resolve_sentiment=resolve_sentiment
        )
        run.briefing = briefing
        with record_web_searches() as research, llm_trace(f"orchestrator-run-{run.id}"):
            decision = agent.decide(briefing, model=orchestrator.model)
        run.decision = decision.model_dump()
        run.research = research
        # Validate and apply atomically: an unexpected error rolls back every action.
        with db.begin_nested():
            validated = validate_decision(decision, decision_state(db, orchestrator))
            applied, rejected = _apply(db, orchestrator, validated)
    except OrchestratorUnavailableError as exc:
        # The briefing and any research made before the failure stay on the run.
        run.research = research
        _finish(db, run, OrchestratorRunStatus.FAILED, started=started, error=str(exc))
        _notify_failure(notifier, run, orchestrator)
        return run
    except Exception as exc:
        logger.exception("orchestrator run %s failed", run_id)
        db.rollback()
        message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        run = get_run(db, run_id)
        orchestrator = service.get_orchestrator(db, run.orchestrator_id)
        run.research = research
        _finish(db, run, OrchestratorRunStatus.FAILED, started=started, error=message)
        _notify_failure(notifier, run, orchestrator)
        return run

    status, error = _outcome(decision, applied, rejected)
    run.applied = applied
    run.rejected = rejected
    run.research = research
    _finish(db, run, status, started=started, error=error)
    if status is OrchestratorRunStatus.FAILED:
        _notify_failure(notifier, run, orchestrator)
    else:
        _notify_summary(notifier, run, orchestrator)
    return run


# Notifications ---------------------------------------------------------------
def _describe(action: dict[str, Any]) -> str:
    """'Preset name on TICKER, TICKER' for an applied action."""
    key = action.get("preset_key")
    try:
        name = presets.get_preset(key).display_name if key else "custom bot"
    except UnknownPresetError:
        name = key or "custom bot"
    tickers = ", ".join(action.get("tickers") or [])
    return f"{name} on {tickers}" if tickers else name


def _send(notifier: Notifier, message: str, title: str) -> None:
    """Best-effort push: a notifier failure never changes the run's outcome."""
    try:
        notifier.send(message, title=title)
    except Exception:
        logger.warning("orchestrator notification failed", exc_info=True)


def _notify_summary(
    notifier: Notifier | None, run: BotOrchestratorRun, orchestrator: BotOrchestrator
) -> None:
    """Push a summary of a scheduled run's applied actions (manual runs stay silent)."""
    if notifier is None or run.trigger != OrchestratorTrigger.SCHEDULED.value:
        return
    applied = run.applied or []
    deployed = [_describe(a) for a in applied if a["kind"] == "deploy"]
    stopped = [_describe(a) for a in applied if a["kind"] == "stop"]
    parts = []
    if deployed:
        parts.append("Deployed: " + "; ".join(deployed) + ".")
    if stopped:
        parts.append("Stopped: " + "; ".join(stopped) + ".")
    if run.rejected:
        parts.append(f"{len(run.rejected)} action(s) rejected.")
    if not parts:
        parts.append("No changes today.")
    _send(notifier, " ".join(parts), f"Orchestrator {orchestrator.label}")


def _notify_failure(
    notifier: Notifier | None, run: BotOrchestratorRun, orchestrator: BotOrchestrator
) -> None:
    """Push a failure notice for a scheduled run (manual runs stay silent)."""
    if notifier is None or run.trigger != OrchestratorTrigger.SCHEDULED.value:
        return
    _send(
        notifier,
        f"Decision run failed: {run.error or 'unknown error'}",
        f"Orchestrator {orchestrator.label}",
    )
