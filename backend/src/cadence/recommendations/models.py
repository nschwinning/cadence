"""SQLAlchemy 2.0 ORM model for recommendation runs.

Schema is owned by Alembic; this model is the source of truth for autogenerate.
The whole run — request, agent prompt, tool-call count, per-candidate results,
and any failure reason — lives on a single row, with the results kept as a JSONB
breakdown (one entry per candidate).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cadence.database import Base
from cadence.recommendations.constants import RunPhase


class RecommendationRun(Base):
    """A single AI asset-recommendation run and its recorded outcome.

    ``requested_categories`` and ``results`` are JSONB. ``results`` is a list of
    ``{"ticker": str, "outcome": str, "detail": str | None}`` objects, one per
    candidate the agent returned. ``prompt`` is the exact text sent to the agent;
    ``tool_call_count`` is how many tool calls the agent made.
    """

    __tablename__ = "recommendation_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # One of cadence.recommendations.constants.RunPhase values.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=RunPhase.QUEUED.value
    )
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_call_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
