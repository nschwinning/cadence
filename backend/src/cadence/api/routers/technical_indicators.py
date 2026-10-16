"""Technical-indicator router. Mounted under ``/api/v1``.

Exposes a single cron-guarded trigger that starts the nightly indicator precompute
in the background and returns immediately. Guarded by the shared ``X-Cron-Token``
header (empty config rejects all), reusing the AI-portfolio cron dependency.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cadence.api.cron_auth import require_valid_cron_token
from cadence.api.schemas import (
    AssetIndicatorResponse,
    TechnicalIndicatorConfig,
    TechnicalIndicatorRunResponse,
    WatchlistIndicatorRead,
    WatchlistIndicatorsResponse,
)
from cadence.assets.errors import AssetNotFoundError
from cadence.database import get_db
from cadence.technical_indicators import service
from cadence.technical_indicators.background import (
    TechnicalIndicatorJobRunner,
    default_job_runner,
)
from cadence.technical_indicators.constants import WATCHLIST_MIN_BARS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/technical-indicators", tags=["technical-indicators"])


def get_technical_indicator_job_runner() -> TechnicalIndicatorJobRunner:
    """Provide the process-wide indicator job runner. Overridden in tests."""
    return default_job_runner


DbSession = Annotated[Session, Depends(get_db)]
JobRunner = Annotated[
    TechnicalIndicatorJobRunner, Depends(get_technical_indicator_job_runner)
]


@router.get("/config", response_model=TechnicalIndicatorConfig)
def get_indicator_config() -> TechnicalIndicatorConfig:
    """Return the configured technical-indicator setup for display.

    A plain read (NOT cron-guarded): the indicator set with its period/lookback
    parameters, the deterministic uptrend trend-gate rules and thresholds, and
    the reversal-flag definitions and thresholds, sourced from the live
    configuration. Does not start or alter any computation.
    """
    return TechnicalIndicatorConfig.model_validate(service.get_indicator_config())


@router.get("/watchlist", response_model=WatchlistIndicatorsResponse)
def list_watchlist_indicators(db: DbSession) -> WatchlistIndicatorsResponse:
    """Return the short-window technical profile for every watchlist asset.

    A plain read (NOT cron-guarded). One batched response for all watchlist
    assets: the momentum / mean-reversion subset per asset, each flagged
    ``insufficient_history`` when below the minimum-bars floor. The long-window
    indicators and the uptrend trend-gate verdict are deliberately not exposed
    here — they are not a meaningful trading signal for emerging names.
    """
    return WatchlistIndicatorsResponse(
        min_bars=WATCHLIST_MIN_BARS,
        items=[
            WatchlistIndicatorRead.model_validate(snap)
            for snap in service.get_watchlist_indicators(db)
        ],
    )


@router.get("/assets/{ticker}", response_model=AssetIndicatorResponse)
def get_asset_indicators(ticker: str, db: DbSession) -> AssetIndicatorResponse:
    """Return the short-window technical profile for a single asset by ticker.

    A plain read (NOT cron-guarded) that serves an asset of any membership —
    universe or watchlist — since the underlying snapshots are computed
    universe-wide. The profile is flagged ``insufficient_history`` when the asset
    is below the minimum-bars floor or has no snapshot yet. The long-window
    indicators and the uptrend trend-gate verdict are deliberately not exposed.
    Responds 404 when the ticker is not in the universe.
    """
    try:
        snapshot = service.get_asset_indicators(db, ticker)
    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return AssetIndicatorResponse(
        min_bars=WATCHLIST_MIN_BARS,
        indicator=WatchlistIndicatorRead.model_validate(snapshot),
    )


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
