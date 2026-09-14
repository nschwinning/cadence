"""In-process background execution for AI portfolio build/rebalance jobs.

Mirrors the recommendations job runner: jobs run on a dedicated single-worker
thread pool so at most one job is in flight at a time. Each job opens its own
session, drives the service, and records the outcome. An event whose worker dies
without reaching a terminal status is reaped on the next status read; events left
non-terminal by a process restart are failed at startup.

Unlike the recommendations runner (a single global run guard), rebalance jobs are
guarded **per session**: a session with a queued/running rebalance is not started
again — the in-flight event is returned instead, so the daily fan-out and the
manual trigger both skip sessions already rebalancing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from threading import Lock
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.ai_portfolio import service
from cadence.ai_portfolio.agent import AIPortfolioAgent
from cadence.ai_portfolio.constants import TERMINAL_STATUSES, EventStatus
from cadence.ai_portfolio.models import AIPortfolioEvent
from cadence.ai_portfolio.service import AIBuildParams
from cadence.broker.base import Broker
from cadence.database import SessionLocal

SessionFactory = Callable[[], AbstractContextManager[Session]]

_TERMINAL_STATUS_VALUES = [status.value for status in TERMINAL_STATUSES]


@contextmanager
def _open_session() -> Iterator[Session]:
    """Default session factory: a fresh ``SessionLocal`` per job."""
    with SessionLocal() as session:
        yield session


class _Executor(Protocol):
    """Minimal executor seam so tests can defer or inline job execution."""

    def submit(self, fn: Callable[..., object], /, *args: object) -> Future[None]: ...


class AIPortfolioJobRunner:
    """Owns the worker pool and the map of in-flight event futures.

    Injectable ``session_factory``/``executor`` let tests run jobs on the test
    session and control when they execute.
    """

    def __init__(
        self,
        session_factory: SessionFactory = _open_session,
        executor: _Executor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._executor: _Executor = executor or cast(
            "_Executor",
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cadence-ai"),
        )
        self._active: dict[uuid.UUID, Future[None]] = {}
        self._lock = Lock()

    # Build -----------------------------------------------------------------
    def start_build(
        self,
        session: Session,
        params: AIBuildParams,
        agent: AIPortfolioAgent,
        broker: Broker,
    ) -> AIPortfolioEvent:
        """Create and submit a build event; return it (validation errors propagate)."""
        with self._lock:
            event = service.create_build_event(session, params)
            future = self._executor.submit(self._job_build, event.id, agent, broker)
            self._active[event.id] = future
        return event

    # Rebalance -------------------------------------------------------------
    def start_rebalance(
        self,
        session: Session,
        session_id: uuid.UUID,
        agent: AIPortfolioAgent,
        broker: Broker,
    ) -> tuple[AIPortfolioEvent, bool]:
        """Create and submit a rebalance event, or return the in-flight one.

        Returns ``(event, started)``. When a rebalance is already queued/running
        for the session, that event is returned with ``started=False`` and no new
        event is created (per-session concurrency guard). A guard event whose
        worker has died is reaped first, so a fresh rebalance can proceed.
        """
        with self._lock:
            self._prune_locked()
            existing = service.get_inflight_rebalance_event(session, session_id)
            if existing is not None and not self._maybe_reap(session, existing):
                return existing, False

            event = service.create_rebalance_event(session, session_id)
            future = self._executor.submit(self._job_rebalance, event.id, agent, broker)
            self._active[event.id] = future
        return event, True

    # Status ----------------------------------------------------------------
    def status(self, session: Session, event_id: uuid.UUID) -> AIPortfolioEvent:
        """Return an event, reaping a dead worker (done future, non-terminal DB)."""
        event = service.get_event(session, event_id)
        self._maybe_reap(session, event)
        return event

    # Internal --------------------------------------------------------------
    def _maybe_reap(self, session: Session, event: AIPortfolioEvent) -> bool:
        """Fail ``event`` if its worker finished without a terminal status.

        Returns ``True`` when the event is terminal after this call.
        """
        if event.status in _TERMINAL_STATUS_VALUES:
            return True
        future = self._active.get(event.id)
        if future is not None and future.done():
            event.status = EventStatus.FAILED.value
            event.error = self._dead_worker_reason(future)
            session.commit()
            return True
        return False

    def _job_build(
        self, event_id: uuid.UUID, agent: AIPortfolioAgent, broker: Broker
    ) -> None:
        with self._session_factory() as session:
            service.run_build_event(session, event_id, agent, broker)

    def _job_rebalance(
        self, event_id: uuid.UUID, agent: AIPortfolioAgent, broker: Broker
    ) -> None:
        with self._session_factory() as session:
            service.run_rebalance_event(session, event_id, agent, broker)

    def _prune_locked(self) -> None:
        """Drop finished futures from the active map."""
        for event_id, future in list(self._active.items()):
            if future.done():
                del self._active[event_id]

    @staticmethod
    def _dead_worker_reason(future: Future[None]) -> str:
        exc = future.exception()
        if exc is not None:
            return f"{type(exc).__name__}: {exc}"
        return "worker terminated without completing the event"


def mark_orphaned_events_failed(session: Session) -> int:
    """Fail every non-terminal event (called at startup after a restart).

    Returns the number of events marked failed.
    """
    orphans = list(
        session.execute(
            select(AIPortfolioEvent).where(
                AIPortfolioEvent.status.notin_(_TERMINAL_STATUS_VALUES)
            )
        ).scalars()
    )
    for event in orphans:
        event.status = EventStatus.FAILED.value
        event.error = "orphaned by restart"
    if orphans:
        session.commit()
    return len(orphans)


def cleanup_orphaned_events_on_startup() -> int:
    """Open a session and fail any events left non-terminal by a prior process."""
    with _open_session() as session:
        return mark_orphaned_events_failed(session)


#: Process-wide job runner used by the API.
default_job_runner = AIPortfolioJobRunner()
