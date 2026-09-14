"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cadence.ai_portfolio.background import cleanup_orphaned_events_on_startup
from cadence.api.routers import (
    ai_portfolio_router,
    assets_router,
    dashboard_router,
    health_router,
    paper_trading_router,
    portfolios_router,
    recommendations_router,
)
from cadence.config import settings
from cadence.recommendations.background import cleanup_orphaned_runs_on_startup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan. Schema is owned by Alembic; no table creation here.

    On startup, any recommendation run or AI portfolio event left non-terminal by
    a prior process (e.g. a restart mid-job) is marked failed so it never appears
    stuck.
    """
    cleanup_orphaned_runs_on_startup()
    cleanup_orphaned_events_on_startup()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health is unprefixed; resource routers mount under /api/v1.
    app.include_router(health_router)
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(recommendations_router, prefix="/api/v1")
    app.include_router(portfolios_router, prefix="/api/v1")
    app.include_router(paper_trading_router, prefix="/api/v1")
    app.include_router(ai_portfolio_router, prefix="/api/v1")

    return app


app = create_app()
