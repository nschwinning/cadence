"""Orchestrator lifecycle, capital pool accounting, and reads.

The capital pool: ``free_capital`` is debited when a bot is deployed (see
:mod:`.runs`) and credited exactly once with a bot's remaining cash when that bot is no
longer active and holds no positions (:func:`settle_returned_capital`). Value and
allocation are computed on read from the orchestrator's unreturned bots, so reads are
correct even before settlement has run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.bot_orchestrator.constants import (
    DEFAULT_MAX_BOT_SHARE,
    DEFAULT_MAX_PARALLEL_BOTS,
    DEFAULT_MAX_TICKERS_PER_BOT,
    MAX_PARALLEL_BOTS,
    MAX_TICKERS_PER_BOT,
    MIN_ORCHESTRATOR_CAPITAL,
    MIN_PARALLEL_BOTS,
    MIN_TICKERS_PER_BOT,
    OrchestratorStatus,
)
from cadence.bot_orchestrator.errors import (
    InvalidOrchestratorConfigError,
    OrchestratorNotArchivableError,
    OrchestratorNotFoundError,
)
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.config import settings
from cadence.paper_trading.constants import AIModel, Benchmark, RebalanceCadence
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotSessionStatus, StopReason
from cadence.strategy_bots.models import BotSession


@dataclass(frozen=True)
class OrchestratorFigures:
    """Computed capital figures and bot counts for one orchestrator."""

    #: Free capital plus the current value of every bot not yet returned.
    value: float
    #: Sum of the initial capital of every bot not yet returned.
    allocated_capital: float
    #: (value - capital) / capital.
    total_return_pct: float
    active_bots: int
    #: Stopped bots whose positions are still being sold.
    liquidating_bots: int


# Lifecycle -------------------------------------------------------------------
def create_orchestrator(
    db: Session,
    *,
    label: str,
    capital: float,
    max_parallel_bots: int = DEFAULT_MAX_PARALLEL_BOTS,
    max_bot_share: float = DEFAULT_MAX_BOT_SHARE,
    max_tickers_per_bot: int = DEFAULT_MAX_TICKERS_PER_BOT,
    cadence: str = RebalanceCadence.DAILY.value,
    model: str | None = None,
    benchmark: str = Benchmark.SP500.value,
) -> BotOrchestrator:
    """Validate and persist an active orchestrator. Invokes no AI, creates no bot."""
    clean_label = label.strip()
    if not clean_label:
        raise InvalidOrchestratorConfigError("a label is required")
    if capital < MIN_ORCHESTRATOR_CAPITAL:
        raise InvalidOrchestratorConfigError(
            f"capital must be at least {MIN_ORCHESTRATOR_CAPITAL:,.0f}"
        )
    if not MIN_PARALLEL_BOTS <= max_parallel_bots <= MAX_PARALLEL_BOTS:
        raise InvalidOrchestratorConfigError(
            f"max_parallel_bots must be between {MIN_PARALLEL_BOTS} and "
            f"{MAX_PARALLEL_BOTS}"
        )
    if not 0.0 < max_bot_share <= 1.0:
        raise InvalidOrchestratorConfigError(
            "max_bot_share must be greater than 0 and at most 1"
        )
    if not MIN_TICKERS_PER_BOT <= max_tickers_per_bot <= MAX_TICKERS_PER_BOT:
        raise InvalidOrchestratorConfigError(
            f"max_tickers_per_bot must be between {MIN_TICKERS_PER_BOT} and "
            f"{MAX_TICKERS_PER_BOT}"
        )
    resolved_model = model or settings.AI_PORTFOLIO_MODEL
    for value, enum, field in (
        (cadence, RebalanceCadence, "cadence"),
        (resolved_model, AIModel, "model"),
        (benchmark, Benchmark, "benchmark"),
    ):
        try:
            enum(value)
        except ValueError as exc:
            raise InvalidOrchestratorConfigError(
                f"{value!r} is not a known {field}"
            ) from exc

    orchestrator = BotOrchestrator(
        label=clean_label,
        status=OrchestratorStatus.ACTIVE.value,
        capital=capital,
        free_capital=capital,
        max_parallel_bots=max_parallel_bots,
        max_bot_share=max_bot_share,
        max_tickers_per_bot=max_tickers_per_bot,
        cadence=cadence,
        model=resolved_model,
        benchmark=benchmark,
    )
    db.add(orchestrator)
    db.flush()
    return orchestrator


def get_orchestrator(db: Session, orchestrator_id: uuid.UUID) -> BotOrchestrator:
    """Load an orchestrator by id, or raise ``OrchestratorNotFoundError``."""
    orchestrator = db.get(BotOrchestrator, orchestrator_id)
    if orchestrator is None:
        raise OrchestratorNotFoundError(str(orchestrator_id))
    return orchestrator


def list_orchestrators(
    db: Session, *, include_archived: bool = False
) -> list[BotOrchestrator]:
    """Orchestrators newest first; archived ones only when requested."""
    stmt = select(BotOrchestrator).order_by(BotOrchestrator.created_at.desc())
    if not include_archived:
        stmt = stmt.where(BotOrchestrator.status != OrchestratorStatus.ARCHIVED.value)
    return list(db.execute(stmt).scalars())


def active_orchestrators(db: Session) -> list[BotOrchestrator]:
    """Every active orchestrator (the scheduled-run working set), oldest first."""
    stmt = (
        select(BotOrchestrator)
        .where(BotOrchestrator.status == OrchestratorStatus.ACTIVE.value)
        .order_by(BotOrchestrator.created_at)
    )
    return list(db.execute(stmt).scalars())


def stop_orchestrator(db: Session, orchestrator_id: uuid.UUID) -> BotOrchestrator:
    """Stop an orchestrator and every active bot it deployed (idempotent).

    Bots are stopped with reason ``orchestrator`` (their positions are sold by the next
    open-market tick); bots that are already flat return their cash immediately.
    """
    orchestrator = get_orchestrator(db, orchestrator_id)
    if orchestrator.status != OrchestratorStatus.ACTIVE.value:
        return orchestrator
    for bot in orchestrator_bots(db, orchestrator):
        if bot.status == BotSessionStatus.ACTIVE.value:
            bot_service.stop_bot_session(db, bot.id, reason=StopReason.ORCHESTRATOR)
    orchestrator.status = OrchestratorStatus.STOPPED.value
    orchestrator.stopped_at = datetime.now(UTC)
    db.flush()
    settle_returned_capital(db, orchestrator)
    return orchestrator


def archive_orchestrator(db: Session, orchestrator_id: uuid.UUID) -> BotOrchestrator:
    """Archive a stopped orchestrator, or raise if it is still active."""
    orchestrator = get_orchestrator(db, orchestrator_id)
    if orchestrator.status == OrchestratorStatus.ARCHIVED.value:
        return orchestrator
    if orchestrator.status != OrchestratorStatus.STOPPED.value:
        raise OrchestratorNotArchivableError("only a stopped orchestrator can be archived")
    orchestrator.status = OrchestratorStatus.ARCHIVED.value
    orchestrator.archived_at = datetime.now(UTC)
    db.flush()
    return orchestrator


# Bots & capital ---------------------------------------------------------------
def orchestrator_bots(db: Session, orchestrator: BotOrchestrator) -> list[BotSession]:
    """Every bot the orchestrator deployed, oldest first."""
    stmt = (
        select(BotSession)
        .where(BotSession.orchestrator_id == orchestrator.id)
        .order_by(BotSession.created_at)
    )
    return list(db.execute(stmt).scalars())


def _is_finished(bot: BotSession) -> bool:
    """A bot that is no longer active and holds no positions (ready to return cash)."""
    return bot.status != BotSessionStatus.ACTIVE.value and not bot.positions


def settle_returned_capital(db: Session, orchestrator: BotOrchestrator) -> float:
    """Return each finished, unreturned bot's cash to the pool exactly once.

    Locks the orchestrator row so concurrent settlements (tick vs. run) cannot credit
    the same bot twice. Returns the amount credited by this call.
    """
    db.execute(
        select(BotOrchestrator.id)
        .where(BotOrchestrator.id == orchestrator.id)
        .with_for_update()
    )
    stmt = (
        select(BotSession)
        .where(BotSession.orchestrator_id == orchestrator.id)
        .where(BotSession.capital_returned_at.is_(None))
        .where(BotSession.status != BotSessionStatus.ACTIVE.value)
    )
    credited = 0.0
    now = datetime.now(UTC)
    for bot in db.execute(stmt).scalars():
        if not _is_finished(bot):
            continue
        credited += bot.cash
        bot.capital_returned_at = now
    if credited:
        orchestrator.free_capital += credited
    db.flush()
    return credited


def settle_all_returned_capital(db: Session) -> float:
    """Settle every orchestrator that has a finished, unreturned bot (tick hook)."""
    stmt = (
        select(BotOrchestrator)
        .join(BotSession, BotSession.orchestrator_id == BotOrchestrator.id)
        .where(BotSession.capital_returned_at.is_(None))
        .where(BotSession.status != BotSessionStatus.ACTIVE.value)
        .distinct()
    )
    return sum(
        settle_returned_capital(db, orchestrator)
        for orchestrator in db.execute(stmt).scalars()
    )


def bot_value(db: Session, bot: BotSession) -> float:
    """A deployed bot's value: its cash once finished, else its live value."""
    if _is_finished(bot):
        return bot.cash
    return bot_service.bot_current_value(db, bot)


def orchestrator_figures(
    db: Session, orchestrator: BotOrchestrator
) -> OrchestratorFigures:
    """Value, allocation, return and bot counts computed from the unreturned bots."""
    value = orchestrator.free_capital
    allocated = 0.0
    active = 0
    liquidating = 0
    for bot in orchestrator_bots(db, orchestrator):
        if bot.status == BotSessionStatus.ACTIVE.value:
            active += 1
        elif bot.positions:
            liquidating += 1
        if bot.capital_returned_at is not None:
            continue
        value += bot_value(db, bot)
        allocated += bot.initial_capital
    total_return = (value - orchestrator.capital) / orchestrator.capital
    return OrchestratorFigures(
        value=value,
        allocated_capital=allocated,
        total_return_pct=total_return,
        active_bots=active,
        liquidating_bots=liquidating,
    )
