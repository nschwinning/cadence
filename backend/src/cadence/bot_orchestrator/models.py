"""ORM models for the bot orchestrator.

* ``BotOrchestrator`` — the user-configured orchestrator: limits, cadence, model, and
  the capital pool's ``free_capital`` (deploys debit it; stopped, flat bots credit their
  final cash back exactly once).
* ``BotOrchestratorRun`` — one decision run's full audit trail (briefing, AI decision,
  applied and rejected actions, research, error). A partial unique index allows at most
  one queued-or-running run per orchestrator.

Deployed bots reference their orchestrator via ``bot_sessions.orchestrator_id``; the
strategy-bot models deliberately carry only that column (no relationship back here).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cadence.bot_orchestrator.constants import (
    OrchestratorRunStatus,
    OrchestratorStatus,
)
from cadence.database import Base


def _enum_column(enum: type[Enum]) -> SQLEnum:
    """A non-native enum column storing the member ``value``."""
    return SQLEnum(
        enum,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
    )


class BotOrchestrator(Base):
    """An AI orchestrator managing a pool of capital across preset strategy bots."""

    __tablename__ = "bot_orchestrators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        _enum_column(OrchestratorStatus),
        nullable=False,
        server_default=OrchestratorStatus.ACTIVE.value,
    )
    # The capital pool the orchestrator was deployed with.
    capital: Mapped[float] = mapped_column(Float, nullable=False)
    # Unallocated cash in the pool; never negative.
    free_capital: Mapped[float] = mapped_column(Float, nullable=False)
    max_parallel_bots: Mapped[int] = mapped_column(Integer, nullable=False)
    # Max share (0, 1] of the orchestrator's value a single bot may receive.
    max_bot_share: Mapped[float] = mapped_column(Float, nullable=False)
    max_tickers_per_bot: Mapped[int] = mapped_column(Integer, nullable=False)
    # A RebalanceCadence value (daily / weekly / monthly).
    cadence: Mapped[str] = mapped_column(Text, nullable=False)
    # An AIModel value used for every decision run.
    model: Mapped[str] = mapped_column(Text, nullable=False)
    # A Benchmark value, also applied to every bot it deploys.
    benchmark: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    runs: Mapped[list[BotOrchestratorRun]] = relationship(
        back_populates="orchestrator",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BotOrchestratorRun.created_at.desc()",
    )


class BotOrchestratorRun(Base):
    """One decision run of an orchestrator, with its full audit trail."""

    __tablename__ = "bot_orchestrator_runs"
    __table_args__ = (
        Index("idx_orchestrator_runs_created", "orchestrator_id", "created_at"),
        # At most one queued-or-running run per orchestrator.
        Index(
            "uq_orchestrator_live_run",
            "orchestrator_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    orchestrator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_orchestrators.id", ondelete="CASCADE"),
        nullable=False,
    )
    # An OrchestratorTrigger value.
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        _enum_column(OrchestratorRunStatus),
        nullable=False,
        server_default=OrchestratorRunStatus.QUEUED.value,
    )
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    briefing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # The AI's structured output (model_dump).
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    applied: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    rejected: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    # Web searches the AI made during the run.
    research: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    orchestrator: Mapped[BotOrchestrator] = relationship(back_populates="runs")
