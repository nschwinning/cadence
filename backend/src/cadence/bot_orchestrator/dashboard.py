"""Dashboard rows for bot orchestrators (``kind='orchestrator'``).

An orchestrator appears on the dashboard as one row covering its free capital and all
of its bots; the bots it deployed are excluded from the bot rows
(:func:`cadence.strategy_bots.service.dashboard_performances`). That way the dashboard
counts orchestrator money exactly once: free capital is included, a stopped bot's
returned cash stays in the figure, and capital recycled into a new bot is not read as
a fresh contribution — the capital pool is the row's single contribution.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.bot_orchestrator import service
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorSnapshot
from cadence.dashboard.constants import DashboardRange, resolve_range_start
from cadence.dashboard.service import (
    SessionContribution,
    SessionPerformance,
    SessionValuePoint,
)
from cadence.paper_trading.benchmark import (
    Contribution,
    load_benchmark_series,
    rebased_benchmark_value,
)
from cadence.strategy_bots import service as bot_service


def _snapshots(db: Session, orchestrator: BotOrchestrator) -> list[BotOrchestratorSnapshot]:
    return list(
        db.execute(
            select(BotOrchestratorSnapshot)
            .where(BotOrchestratorSnapshot.orchestrator_id == orchestrator.id)
            .order_by(BotOrchestratorSnapshot.snapshot_date)
        ).scalars()
    )


def dashboard_performance(
    db: Session,
    orchestrator: BotOrchestrator,
    *,
    range_: DashboardRange,
    today: date | None = None,
) -> SessionPerformance:
    """Adapt one orchestrator to a dashboard row, mirroring the bot adapter's rules."""
    as_of = today or datetime.now(UTC).date()
    start_date = resolve_range_start(range_, today=as_of)
    snapshots = _snapshots(db, orchestrator)
    capital = orchestrator.capital
    current_value = service.orchestrator_figures(db, orchestrator).value

    # Daily series from the orchestrator's snapshots; before the first snapshot, one
    # live point keeps the equity line aligned with the benchmark overlay.
    if snapshots:
        points = [
            SessionValuePoint(date=s.snapshot_date, value=s.value)
            for s in snapshots
            if start_date is None or s.snapshot_date >= start_date
        ]
    else:
        points = [SessionValuePoint(date=as_of, value=current_value)]

    if start_date is None:
        value_start = capital
    else:
        prior = [s.value for s in snapshots if s.snapshot_date <= start_date]
        value_start = prior[-1] if prior else capital

    # The capital pool is the single contribution, however often capital is recycled.
    contrib_date = snapshots[0].snapshot_date if snapshots else as_of
    contributions = [SessionContribution(effective_date=contrib_date, amount=capital)]
    benchmark_value = rebased_benchmark_value(
        load_benchmark_series(db, orchestrator.benchmark),
        contributions=[Contribution(effective_date=contrib_date, amount=capital)],
        as_of=as_of,
    )

    # Realised P&L and fees accrue across every bot it ever deployed (a stopped bot's
    # results still belong to the orchestrator); unrealised only where capital is
    # still out in a bot. Reuse the bot adapter so the semantics match bot rows.
    realised = 0.0
    unrealised = 0.0
    fees = 0.0
    for bot in service.orchestrator_bots(db, orchestrator):
        row = bot_service.dashboard_performance(db, bot, range_=range_, today=as_of)
        realised += row.realised_pnl
        fees += row.fees
        if bot.capital_returned_at is None:
            unrealised += row.unrealised_pnl

    return SessionPerformance(
        id=orchestrator.id,
        label=orchestrator.label,
        allocated_capital=capital,
        current_value=current_value,
        pnl=current_value - value_start,
        realised_pnl=realised,
        unrealised_pnl=unrealised,
        fees=fees,
        points=points,
        contributions=contributions,
        benchmark_value=benchmark_value,
        kind="orchestrator",
    )


def dashboard_performances(
    db: Session, *, range_: DashboardRange, today: date | None = None
) -> list[SessionPerformance]:
    """One dashboard row per active orchestrator."""
    return [
        dashboard_performance(db, orchestrator, range_=range_, today=today)
        for orchestrator in service.active_orchestrators(db)
    ]
