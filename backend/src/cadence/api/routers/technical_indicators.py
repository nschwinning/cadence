"""Technical-indicator router. Mounted under ``/api/v1``.

Exposes a single cron-guarded trigger that starts the nightly indicator precompute
in the background and returns immediately. Guarded by the shared ``X-Cron-Token``
header (empty config rejects all), reusing the AI-portfolio cron dependency.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from cadence.api.routers.ai_portfolio import require_valid_cron_token
from cadence.api.schemas import TechnicalIndicatorRunResponse
from cadence.database import get_db
from cadence.technical_indicators.background import (
    TechnicalIndicatorJobRunner,
    default_job_runner,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/technical-indicators", tags=["technical-indicators"])


def get_technical_indicator_job_runner() -> TechnicalIndicatorJobRunner:
    """Provide the process-wide indicator job runner. Overridden in tests."""
    return default_job_runner


DbSession = Annotated[Session, Depends(get_db)]
JobRunner = Annotated[
    TechnicalIndicatorJobRunner, Depends(get_technical_indicator_job_runner)
]


@router.post(
    "/runs",
    response_model=TechnicalIndicatorRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_indicator_run(
    db: DbSession,
    runner: JobRunner,
    _token: Annotated[None, Depends(require_valid_cron_token)],
) -> TechnicalIndicatorRunResponse:
    """Start the technical-indicator precompute over the whole universe.

    Guarded by the ``X-Cron-Token`` header. Starts the run on the single-worker
    background pool and returns immediately. If a run is already in flight, that
    run is returned with ``started=False`` rather than starting a second one.
    """
    run, started = runner.start_run(db)
    return TechnicalIndicatorRunResponse(
        run_id=run.id, status=run.status, started=started
    )
