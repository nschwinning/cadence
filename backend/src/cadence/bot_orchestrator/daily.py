"""End-of-day orchestrator snapshots and the daily P&L push.

Runs from the evening bot snapshot job, after the bots' own snapshots, so each bot's
day P&L is available. Per active orchestrator it settles returned capital, upserts a
:class:`BotOrchestratorSnapshot`, and sends one best-effort push covering the
orchestrator and its bots (the bots it deployed send no push of their own). The
message builder is pure; :func:`run_orchestrator_daily` does the reads.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio.scheduling import MARKET_TIMEZONE
from cadence.bot_orchestrator import service
from cadence.bot_orchestrator.models import (
    BotOrchestrator,
    BotOrchestratorRun,
    BotOrchestratorSnapshot,
)
from cadence.notify.base import Notifier
from cadence.paper_trading.benchmark import (
    benchmark_return_fraction,
    load_benchmark_series,
)
from cadence.paper_trading.constants import Benchmark, benchmark_display_name
from cadence.strategy_bots import presets
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import (
    STRATEGY_DISPLAY_NAMES,
    BotSessionStatus,
    StopReason,
    StrategyKey,
)
from cadence.strategy_bots.errors import UnknownPresetError
from cadence.strategy_bots.models import BotSession, BotValueSnapshot
from cadence.strategy_bots.notifications import _signed_money, _signed_pct

logger = logging.getLogger(__name__)

#: Bots listed per Started / Stopped line before summarising the rest as a count.
_MAX_LISTED_BOTS = 5
#: Characters of a failed run's error shown in the push.
_MAX_ERROR_CHARS = 80

_STOP_REASON_LABELS: dict[str, str] = {
    StopReason.ORCHESTRATOR.value: "orchestrator",
    StopReason.DRAWDOWN_KILL_SWITCH.value: "kill-switch",
    StopReason.MANUAL.value: "manual",
}


# Snapshots -------------------------------------------------------------------
def record_orchestrator_snapshot(
    db: Session, orchestrator: BotOrchestrator, snapshot_date: date
) -> BotOrchestratorSnapshot:
    """Settle returned capital, then upsert the orchestrator's snapshot for the date."""
    service.settle_returned_capital(db, orchestrator)
    figures = service.orchestrator_figures(db, orchestrator)
    snapshot = db.execute(
        select(BotOrchestratorSnapshot).where(
            BotOrchestratorSnapshot.orchestrator_id == orchestrator.id,
            BotOrchestratorSnapshot.snapshot_date == snapshot_date,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = BotOrchestratorSnapshot(
            orchestrator_id=orchestrator.id, snapshot_date=snapshot_date
        )
        db.add(snapshot)
    snapshot.value = figures.value
    snapshot.free_capital = orchestrator.free_capital
    snapshot.allocated_capital = figures.allocated_capital
    snapshot.active_bots = figures.active_bots
    db.flush()
    return snapshot


def previous_orchestrator_snapshot(
    db: Session, orchestrator: BotOrchestrator, *, before: date
) -> BotOrchestratorSnapshot | None:
    """The newest snapshot strictly before ``before``."""
    return (
        db.execute(
            select(BotOrchestratorSnapshot)
            .where(
                BotOrchestratorSnapshot.orchestrator_id == orchestrator.id,
                BotOrchestratorSnapshot.snapshot_date < before,
            )
            .order_by(BotOrchestratorSnapshot.snapshot_date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def first_orchestrator_snapshot(
    db: Session, orchestrator: BotOrchestrator
) -> BotOrchestratorSnapshot | None:
    """The orchestrator's earliest snapshot (the benchmark comparison's start)."""
    return (
        db.execute(
            select(BotOrchestratorSnapshot)
            .where(BotOrchestratorSnapshot.orchestrator_id == orchestrator.id)
            .order_by(BotOrchestratorSnapshot.snapshot_date.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )


# Message ---------------------------------------------------------------------
@dataclass(frozen=True)
class StartedBot:
    name: str
    capital: float


@dataclass(frozen=True)
class StoppedBot:
    name: str
    reason: str | None
    return_pct: float


@dataclass(frozen=True)
class DailyFigures:
    """Everything the daily push shows, gathered by :func:`run_orchestrator_daily`."""

    value: float
    day_change: float
    #: ``None`` when the baseline was not positive.
    day_change_pct: float | None
    total_return: float
    total_return_pct: float
    free_capital: float
    allocated_capital: float
    active_bots: int
    max_bots: int
    benchmark_name: str | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    #: (bot name, today's P&L) for active bots with a snapshot today.
    bot_pnls: Sequence[tuple[str, float]] = field(default_factory=tuple)
    started: Sequence[StartedBot] = field(default_factory=tuple)
    stopped: Sequence[StoppedBot] = field(default_factory=tuple)
    #: Status of today's newest decision run; ``None`` when there was none.
    run_status: str | None = None
    run_error: str | None = None


def _capped(items: list[str]) -> str:
    shown = items[:_MAX_LISTED_BOTS]
    hidden = len(items) - len(shown)
    text = "; ".join(shown)
    return f"{text}; +{hidden} more" if hidden > 0 else text


def _bot_line(bot_pnls: Sequence[tuple[str, float]]) -> str | None:
    if not bot_pnls:
        return None
    if len(bot_pnls) == 1:
        name, pnl = bot_pnls[0]
        return f"Only bot: {name} {_signed_money(pnl)}"
    ranked = sorted(bot_pnls, key=lambda item: item[1])
    worst, best = ranked[0], ranked[-1]
    return (
        f"Best: {best[0]} {_signed_money(best[1])} · "
        f"Worst: {worst[0]} {_signed_money(worst[1])}"
    )


def _decision_line(status: str | None, error: str | None) -> str:
    if status is None:
        return "No decision run today"
    if status == "failed" and error:
        short = error if len(error) <= _MAX_ERROR_CHARS else error[: _MAX_ERROR_CHARS - 1] + "…"
        return f"Decision run: failed — {short}"
    return f"Decision run: {status}"


def orchestrator_daily_message(figures: DailyFigures) -> str:
    """Build the orchestrator's evening push body (the label lives in the title)."""
    if figures.day_change_pct is not None:
        value_line = (
            f"${figures.value:,.2f} today "
            f"({_signed_money(figures.day_change)}, {_signed_pct(figures.day_change_pct)})"
        )
    else:
        value_line = f"${figures.value:,.2f} today ({_signed_money(figures.day_change)})"
    lines = [
        value_line,
        (
            f"Total return: {_signed_money(figures.total_return)} "
            f"({_signed_pct(figures.total_return_pct)})"
        ),
        (
            f"Free ${figures.free_capital:,.2f} · "
            f"Allocated ${figures.allocated_capital:,.2f} · "
            f"Bots {figures.active_bots}/{figures.max_bots}"
        ),
    ]
    if (
        figures.benchmark_name is not None
        and figures.benchmark_return is not None
        and figures.excess_return is not None
    ):
        lines.append(
            f"vs {figures.benchmark_name}: {_signed_pct(figures.benchmark_return)} "
            f"(excess {_signed_pct(figures.excess_return)})"
        )
    bot_line = _bot_line(figures.bot_pnls)
    if bot_line is not None:
        lines.append(bot_line)
    started = [f"{b.name} (${b.capital:,.2f})" for b in figures.started]
    lines.append(f"Started: {_capped(started)}" if started else "Started: none")
    stopped = [
        f"{b.name} — {_STOP_REASON_LABELS.get(b.reason or '', 'stopped')} "
        f"({_signed_pct(b.return_pct)})"
        for b in figures.stopped
    ]
    lines.append(f"Stopped: {_capped(stopped)}" if stopped else "Stopped: none")
    lines.append(_decision_line(figures.run_status, figures.run_error))
    return "\n".join(lines)


# Job ---------------------------------------------------------------------------
def _bot_name(bot: BotSession) -> str:
    """'Preset name on TICKER, TICKER' (strategy name when there is no preset)."""
    name: str
    try:
        name = presets.get_preset(bot.preset_key).display_name if bot.preset_key else ""
    except UnknownPresetError:
        name = ""
    if not name:
        name = STRATEGY_DISPLAY_NAMES.get(StrategyKey(bot.strategy_key), bot.strategy_key)
    tickers = ", ".join(s.ticker for s in bot.symbols)
    return f"{name} on {tickers}" if tickers else name


def _market_date(moment: datetime) -> date:
    return moment.astimezone(MARKET_TIMEZONE).date()


def _todays_run(
    db: Session, orchestrator: BotOrchestrator, market_day: date
) -> BotOrchestratorRun | None:
    runs = db.execute(
        select(BotOrchestratorRun)
        .where(BotOrchestratorRun.orchestrator_id == orchestrator.id)
        .order_by(BotOrchestratorRun.created_at.desc())
        .limit(10)
    ).scalars()
    return next((r for r in runs if _market_date(r.created_at) == market_day), None)


def _bot_snapshot(db: Session, bot: BotSession, snapshot_date: date) -> BotValueSnapshot | None:
    return db.execute(
        select(BotValueSnapshot).where(
            BotValueSnapshot.bot_session_id == bot.id,
            BotValueSnapshot.snapshot_date == snapshot_date,
        )
    ).scalar_one_or_none()


def gather_daily_figures(
    db: Session,
    orchestrator: BotOrchestrator,
    snapshot: BotOrchestratorSnapshot,
    *,
    now: datetime,
) -> DailyFigures:
    """Collect the push's figures for one orchestrator after its snapshot is recorded."""
    previous = previous_orchestrator_snapshot(db, orchestrator, before=snapshot.snapshot_date)
    baseline = previous.value if previous is not None else orchestrator.capital
    day_change = snapshot.value - baseline
    total_return = snapshot.value - orchestrator.capital

    benchmark_name = benchmark_return = excess = None
    first = first_orchestrator_snapshot(db, orchestrator)
    if first is not None and first.snapshot_date < snapshot.snapshot_date and first.value > 0:
        series = load_benchmark_series(db, orchestrator.benchmark)
        benchmark_return = benchmark_return_fraction(
            series, start_date=first.snapshot_date, as_of=snapshot.snapshot_date
        )
        if benchmark_return is not None:
            benchmark_name = benchmark_display_name(Benchmark(orchestrator.benchmark))
            excess = snapshot.value / first.value - 1.0 - benchmark_return

    market_day = _market_date(now)
    bots = service.orchestrator_bots(db, orchestrator)
    bot_pnls: list[tuple[str, float]] = []
    for bot in bots:
        if bot.status != BotSessionStatus.ACTIVE.value:
            continue
        bot_snapshot = _bot_snapshot(db, bot, snapshot.snapshot_date)
        if bot_snapshot is not None:
            pnl, _ = bot_service.bot_daily_pnl(db, bot, bot_snapshot)
            bot_pnls.append((_bot_name(bot), pnl))
    started = [
        StartedBot(name=_bot_name(b), capital=b.initial_capital)
        for b in bots
        if _market_date(b.created_at) == market_day
    ]
    stopped = [
        StoppedBot(
            name=_bot_name(b),
            reason=b.stop_reason,
            return_pct=service.bot_value(db, b) / b.initial_capital - 1.0,
        )
        for b in bots
        if b.stopped_at is not None and _market_date(b.stopped_at) == market_day
    ]
    run = _todays_run(db, orchestrator, market_day)
    return DailyFigures(
        value=snapshot.value,
        day_change=day_change,
        day_change_pct=day_change / baseline if baseline > 0 else None,
        total_return=total_return,
        total_return_pct=total_return / orchestrator.capital,
        free_capital=snapshot.free_capital,
        allocated_capital=snapshot.allocated_capital,
        active_bots=snapshot.active_bots,
        max_bots=orchestrator.max_parallel_bots,
        benchmark_name=benchmark_name,
        benchmark_return=benchmark_return,
        excess_return=excess,
        bot_pnls=bot_pnls,
        started=started,
        stopped=stopped,
        run_status=run.status if run is not None else None,
        run_error=run.error if run is not None else None,
    )


def run_orchestrator_daily(
    db: Session, *, notifier: Notifier | None, now: datetime | None = None
) -> int:
    """Snapshot every active orchestrator and send its daily push; return the count.

    The snapshot date matches the bot snapshot job's (the job's ``now`` date). A
    ``None`` notifier stays silent and a notifier failure never fails the job.
    """
    moment = now or datetime.now(UTC)
    snapshot_date = moment.date()
    count = 0
    for orchestrator in service.active_orchestrators(db):
        snapshot = record_orchestrator_snapshot(db, orchestrator, snapshot_date)
        count += 1
        if notifier is None:
            continue
        message = orchestrator_daily_message(
            gather_daily_figures(db, orchestrator, snapshot, now=moment)
        )
        try:
            notifier.send(
                message, title=f"Cadence orchestrator: {orchestrator.label} daily P&L"
            )
        except Exception:
            logger.warning("orchestrator daily notification failed", exc_info=True)
    db.flush()
    return count
