"""Enums and fixed limits for the bot orchestrator.

Values are part of the API contract and are stored as free text (non-native enums),
so adding a member needs no migration.
"""

from __future__ import annotations

from enum import StrEnum

from cadence.paper_trading.constants import Benchmark


class OrchestratorStatus(StrEnum):
    """Lifecycle of an orchestrator.

    ``ACTIVE`` orchestrators get decision runs; ``STOPPED`` ones have had every bot
    stopped and get no more runs; ``ARCHIVED`` ones (stopped only) are hidden from the
    default listing.
    """

    ACTIVE = "active"
    STOPPED = "stopped"
    ARCHIVED = "archived"


class OrchestratorRunStatus(StrEnum):
    """State of one decision run (mirrors the AI-portfolio event statuses)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrchestratorTrigger(StrEnum):
    """What started a decision run."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"


#: A run still in flight; at most one per orchestrator (enforced by a partial index).
LIVE_RUN_STATUSES: frozenset[OrchestratorRunStatus] = frozenset(
    {OrchestratorRunStatus.QUEUED, OrchestratorRunStatus.RUNNING}
)

#: Runs that advance the cadence anchor. Failed and skipped runs leave it due.
COUNTING_RUN_STATUSES: frozenset[OrchestratorRunStatus] = frozenset(
    {OrchestratorRunStatus.SUCCEEDED, OrchestratorRunStatus.PARTIAL}
)

#: Smallest capital pool an orchestrator may be deployed with.
MIN_ORCHESTRATOR_CAPITAL = 5_000.0
#: Smallest capital a deployed bot may receive (the build form's bot minimum).
MIN_BOT_CAPITAL = 1_000.0

MIN_PARALLEL_BOTS = 1
MAX_PARALLEL_BOTS = 10
DEFAULT_MAX_PARALLEL_BOTS = 3

#: Default maximum share of the orchestrator's value a single bot may receive.
DEFAULT_MAX_BOT_SHARE = 0.5

MIN_TICKERS_PER_BOT = 1
MAX_TICKERS_PER_BOT = 10
DEFAULT_MAX_TICKERS_PER_BOT = 5

#: Indices whose stored daily closes feed the briefing's market technicals.
BRIEFING_INDICES: tuple[Benchmark, ...] = (
    Benchmark.SP500,
    Benchmark.NASDAQ_100,
    Benchmark.RUSSELL_2000,
)
