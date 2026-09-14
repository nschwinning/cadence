"""Health check router. Performs a real DB round-trip and never crashes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from cadence.api.schemas import DatabaseStatus, HealthResponse, ServiceStatus
from cadence.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Report service and database health.

    Always returns HTTP 200. If the database round-trip fails, the response
    reports a degraded status with the database disconnected rather than raising.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return HealthResponse(
            status=ServiceStatus.DEGRADED,
            database=DatabaseStatus.DISCONNECTED,
        )
    return HealthResponse(
        status=ServiceStatus.OK,
        database=DatabaseStatus.CONNECTED,
    )
