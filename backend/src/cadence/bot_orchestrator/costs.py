"""AI (LLM) cost of orchestrator decision runs and orchestrators.

Every run's AI call is tagged in the LiteLLM spend log with
:func:`~cadence.bot_orchestrator.runs.run_trace_id`, so a run's cost is the spend under
that trace id and an orchestrator's cost is the sum over its runs. Each helper issues at
most one batched spend query. ``None`` means the cost source is unavailable; a run or
orchestrator with no recorded spend reads ``0.0``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorRun
from cadence.bot_orchestrator.runs import run_trace_id
from cadence.paper_trading.ai_cost import cost_source_configured, trace_ai_costs_usd


def run_ai_costs(
    runs: Sequence[BotOrchestratorRun],
) -> dict[uuid.UUID, float] | None:
    """Cost per run id, or ``None`` when the cost source is unavailable."""
    if not cost_source_configured():
        return None
    by_trace = trace_ai_costs_usd([run_trace_id(run.id) for run in runs])
    if by_trace is None:
        return None
    return {run.id: by_trace.get(run_trace_id(run.id), 0.0) for run in runs}


def orchestrator_ai_costs(
    db: Session, orchestrators: Sequence[BotOrchestrator]
) -> dict[uuid.UUID, float] | None:
    """All-time cost per orchestrator id (the sum of its runs' costs).

    ``None`` when the cost source is unavailable; an orchestrator without runs or
    without recorded spend reads ``0.0``.
    """
    if not cost_source_configured():
        return None
    ids = [o.id for o in orchestrators]
    if not ids:
        return {}
    run_rows = db.execute(
        select(BotOrchestratorRun.id, BotOrchestratorRun.orchestrator_id).where(
            BotOrchestratorRun.orchestrator_id.in_(ids)
        )
    ).all()
    by_trace = trace_ai_costs_usd([run_trace_id(run_id) for run_id, _ in run_rows])
    if by_trace is None:
        return None
    totals = dict.fromkeys(ids, 0.0)
    for run_id, orchestrator_id in run_rows:
        totals[orchestrator_id] += by_trace.get(run_trace_id(run_id), 0.0)
    return totals
