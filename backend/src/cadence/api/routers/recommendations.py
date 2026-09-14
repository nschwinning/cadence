"""Recommendations resource router. Mounted under ``/api/v1``.

Creating a run is non-blocking: it queues background work and returns the run
immediately (202). Clients poll ``GET /{run_id}`` until the run reaches a
terminal phase.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cadence.api.schemas import RecommendationRunCreate, RecommendationRunRead
from cadence.assets.market_data import MarketDataProvider, YFinanceMarketDataProvider
from cadence.config import settings
from cadence.database import get_db
from cadence.recommendations import service
from cadence.recommendations.agent import OpenAIRecommenderAgent, RecommenderAgent
from cadence.recommendations.background import (
    RecommendationJobRunner,
    default_job_runner,
)
from cadence.recommendations.errors import (
    RecommendationValidationError,
    RunNotFoundError,
)
from cadence.recommendations.stub import StubRecommenderAgent

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def get_recommender_agent() -> RecommenderAgent:
    """Provide the recommender agent. Overridden with a fake in tests.

    Returns the offline :class:`StubRecommenderAgent` when ``RECOMMENDER_STUB``
    is set (used by the Docker smoke / local dev); otherwise the real agent.
    """
    if settings.RECOMMENDER_STUB:
        return StubRecommenderAgent()
    return OpenAIRecommenderAgent()


def get_market_data_provider() -> MarketDataProvider:
    """Provide the market-data provider. Overridden with a fake in tests."""
    return YFinanceMarketDataProvider()


def get_job_runner() -> RecommendationJobRunner:
    """Provide the process-wide job runner. Overridden in tests."""
    return default_job_runner


DbSession = Annotated[Session, Depends(get_db)]
Agent = Annotated[RecommenderAgent, Depends(get_recommender_agent)]
Provider = Annotated[MarketDataProvider, Depends(get_market_data_provider)]
JobRunner = Annotated[RecommendationJobRunner, Depends(get_job_runner)]


@router.post(
    "",
    response_model=RecommendationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_recommendation_run(
    payload: RecommendationRunCreate,
    db: DbSession,
    agent: Agent,
    provider: Provider,
    job_runner: JobRunner,
) -> RecommendationRunRead:
    """Queue a recommendation run and return it immediately (202)."""
    try:
        run, _started = job_runner.start_run(
            db,
            count=payload.count,
            categories=payload.categories,
            agent=agent,
            provider=provider,
        )
    except RecommendationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return RecommendationRunRead.model_validate(run)


@router.get("", response_model=list[RecommendationRunRead])
def list_recommendation_runs(db: DbSession) -> list[RecommendationRunRead]:
    """Return recent recommendation runs, newest first."""
    return [
        RecommendationRunRead.model_validate(run) for run in service.list_runs(db)
    ]


@router.get("/{run_id}", response_model=RecommendationRunRead)
def get_recommendation_run(
    run_id: int,
    db: DbSession,
    job_runner: JobRunner,
) -> RecommendationRunRead:
    """Return a run's current status and results (reaping a dead worker)."""
    try:
        run = job_runner.status(db, run_id)
    except RunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return RecommendationRunRead.model_validate(run)
