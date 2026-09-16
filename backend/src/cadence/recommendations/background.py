"""In-process background execution for recommendation runs.

Runs execute on a dedicated single-worker thread pool (trading-bot pattern) so
at most one run is in flight at a time. Each job opens its own session, drives
the run executor, and records the outcome. A run whose worker dies without
reaching a terminal phase is reaped on the next status read; runs left
non-terminal by a process restart are failed at startup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from threading import Lock
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.assets.market_data import MarketDataProvider
from cadence.broker.base import Broker
from cadence.database import SessionLocal
from cadence.recommendations.agent import RecommenderAgent
from cadence.recommendations.constants import TERMINAL_PHASES, RunPhase
from cadence.recommendations.models import RecommendationRun
from cadence.recommendations.service import create_run, execute_run, get_run

SessionFactory = Callable[[], AbstractContextManager[Session]]


@contextmanager
def _open_session() -> Iterator[Session]:
    """Default session factory: a fresh ``SessionLocal`` per job."""
    with SessionLocal() as session:
        yield session


class _Executor(Protocol):
    """Minimal executor seam so tests can defer or inline job execution."""

    def submit(self, fn: Callable[..., object], /, *args: object) -> Future[None]: ...


class RecommendationJobRunner:
    """Owns the worker pool and the map of in-flight run futures.

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
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cadence-reco"),
        )
        self._active: dict[int, Future[None]] = {}
        self._lock = Lock()

    def start_run(
        self,
        session: Session,
        count: int,
        categories: list[str],
        agent: RecommenderAgent,
        provider: MarketDataProvider,
        broker: Broker,
    ) -> tuple[RecommendationRun, bool]:
        """Create and submit a run, or return the in-flight one.

        Returns ``(run, started)``. When a run is already in flight, that run is
        returned with ``started=False`` and no new run is created (single-run
        concurrency guard). Validation errors from :func:`create_run` propagate.
        """
        with self._lock:
            inflight_id = self._inflight_locked()
            if inflight_id is not None:
                return get_run(session, inflight_id), False

            run_id = create_run(session, count, categories)
            future = self._executor.submit(
                self._job, run_id, agent, provider, broker
            )
            self._active[run_id] = future

        return get_run(session, run_id), True

    def status(self, session: Session, run_id: int) -> RecommendationRun:
        """Return a run, reaping a dead worker (done future, non-terminal DB)."""
        run = get_run(session, run_id)
        if run.status in TERMINAL_PHASES:
            return run

        future = self._active.get(run_id)
        if future is not None and future.done():
            reason = self._dead_worker_reason(future)
            run.status = RunPhase.FAILED.value
            run.error = reason
            session.commit()
        return run

    def _job(
        self,
        run_id: int,
        agent: RecommenderAgent,
        provider: MarketDataProvider,
        broker: Broker,
    ) -> None:
        with self._session_factory() as session:
            execute_run(session, run_id, agent, provider, broker)

    def _inflight_locked(self) -> int | None:
        """Return the id of a still-running job, pruning finished ones."""
        inflight: int | None = None
        for run_id, future in list(self._active.items()):
            if future.done():
                del self._active[run_id]
            elif inflight is None:
                inflight = run_id
        return inflight

    @staticmethod
    def _dead_worker_reason(future: Future[None]) -> str:
        exc = future.exception()
        if exc is not None:
            return f"{type(exc).__name__}: {exc}"
        return "worker terminated without completing the run"


def mark_orphaned_runs_failed(session: Session) -> int:
    """Fail every non-terminal run (called at startup after a restart).

    Returns the number of runs marked failed.
    """
    orphans = list(
        session.execute(
            select(RecommendationRun).where(
                RecommendationRun.status.notin_(
                    [phase.value for phase in TERMINAL_PHASES]
                )
            )
        ).scalars()
    )
    for run in orphans:
        run.status = RunPhase.FAILED.value
        run.error = "orphaned by restart"
    if orphans:
        session.commit()
    return len(orphans)


def cleanup_orphaned_runs_on_startup() -> int:
    """Open a session and fail any runs left non-terminal by a prior process."""
    with _open_session() as session:
        return mark_orphaned_runs_failed(session)


#: Process-wide job runner used by the API.
default_job_runner = RecommendationJobRunner()
