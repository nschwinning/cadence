"""Dashboard router. Mounted under ``/api/v1``.

Exposes a single read-only endpoint returning an at-a-glance overview of the app
(asset-universe size and composition, portfolio count, paper-trading activity),
computed live from the database. No auth: it reports only aggregate counts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cadence.api.schemas import (
    DashboardAiCostsRead,
    DashboardMetrics,
    DashboardOrchestratorAiCostRead,
    DashboardOverview,
    DashboardPortfolioAiCostRead,
)
from cadence.broker import Broker, get_broker
from cadence.dashboard.constants import DashboardRange
from cadence.dashboard.service import (
    get_dashboard_ai_costs,
    get_dashboard_metrics,
    get_dashboard_overview,
)
from cadence.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_db)]
BrokerDep = Annotated[Broker, Depends(get_broker)]


@router.get("/metrics", response_model=DashboardMetrics)
def read_dashboard_metrics(db: DbSession) -> DashboardMetrics:
    """Return aggregate overview metrics over the current data."""
    return DashboardMetrics.model_validate(get_dashboard_metrics(db))


@router.get("/overview", response_model=DashboardOverview)
def read_dashboard_overview(
    db: DbSession, broker: BrokerDep, range: DashboardRange
) -> DashboardOverview:
    """Return the range-scoped overview over the active sessions.

    ``range`` is a required query parameter; an unsupported value is rejected with
    422 by the enum validation rather than silently defaulted.
    """
    return DashboardOverview.model_validate(
        get_dashboard_overview(db, range_=range, broker=broker)
    )


@router.get("/ai-costs", response_model=DashboardAiCostsRead)
def read_dashboard_ai_costs(db: DbSession) -> DashboardAiCostsRead:
    """Return the all-time AI cost per active portfolio and orchestrator, with a total.

    Range-independent: the figures are cumulative since each session began, so
    there is no ``range`` parameter. Costs degrade to ``null`` when the LiteLLM
    cost source is unavailable rather than failing.
    """
    costs = get_dashboard_ai_costs(db)
    return DashboardAiCostsRead(
        portfolios=[
            DashboardPortfolioAiCostRead(
                session_id=p.session_id, label=p.label, ai_cost_usd=p.ai_cost_usd
            )
            for p in costs.portfolios
        ],
        orchestrators=[
            DashboardOrchestratorAiCostRead(
                orchestrator_id=o.orchestrator_id,
                label=o.label,
                ai_cost_usd=o.ai_cost_usd,
            )
            for o in costs.orchestrators
        ],
        total_ai_cost_usd=costs.total_ai_cost_usd,
    )
