"""Dashboard router. Mounted under ``/api/v1``.

Exposes a single read-only endpoint returning an at-a-glance overview of the app
(asset-universe size and composition, portfolio count, paper-trading activity),
computed live from the database. No auth: it reports only aggregate counts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cadence.api.schemas import DashboardMetrics
from cadence.dashboard.service import get_dashboard_metrics
from cadence.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/metrics", response_model=DashboardMetrics)
def read_dashboard_metrics(db: DbSession) -> DashboardMetrics:
    """Return aggregate overview metrics over the current data."""
    return DashboardMetrics.model_validate(get_dashboard_metrics(db))
