"""In-process background execution for the technical-indicator precompute.

Mirrors the AI-portfolio job runner: the run executes on a dedicated single-worker
thread pool so at most one indicator run is in flight at a time. A second
``start_run`` while one is running is rejected (the in-flight run is returned).
Each job opens its own session and drives the service. A run left non-terminal by
a process restart is failed at startup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from threading import Lock
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence.assets.market_data import MarketDataProvider, YFinanceMarketDataProvider
from cadence.database import SessionLocal
from cadence.technical_indicators import service
from cadence.technical_indicators.constants import TERMINAL_PHASES, RunPhase
from cadence.technical_indicators.models import TechnicalIndicatorRun

SessionFactory = Callable[[], AbstractContextManager[Session]]
ProviderFactory = Callable[[], MarketDataProvider]

_TERMINAL_PHASE_VALUES = [phase.value for phase in TERMINAL_PHASES]


@contextmanager
def _open_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def _default_provider() -> MarketDataProvider:
    return YFinanceMarketDataProvider()


class _Executor(Protocol):
    def submit(self, fn: Callable[..., object], /, *args: object) -> Future[None]: ...


class TechnicalIndicatorJobRunner:
    """Owns the single worker and the one in-flight run guard."""

    def __init__(
        self,
        session_factory: SessionFactory = _open_session,
        provider_factory: ProviderFactory = _default_provider,
        executor: _Executor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._executor: _Executor = executor or cast(
            "_Executor",
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cadence-ti"),
        )
        self._active: Future[None] | None = None
        self._lock = Lock()

    def start_run(self, session: Session) -> tuple[TechnicalIndicatorRun, bool]:
        """Create and submit a run, or return the in-flight one.

        Returns ``(run, started)``. When a run is already in flight, that run is
        returned with ``started=False`` and no new run is created.
        """
        with self._lock:
            if self._active is not None and not self._active.done():
                existing = self._current_inflight(session)
                if existing is not None:
                    return existing, False
            run = service.create_run(session)
            self._active = self._executor.submit(self._job, run.id)
            return run, True

    def status(self, session: Session, run_id: int) -> TechnicalIndicatorRun | None:
        return service.get_run(session, run_id)

    def _current_inflight(
        self, session: Session
    ) -> TechnicalIndicatorRun | None:
        return session.execute(
            select(TechnicalIndicatorRun)
            .where(TechnicalIndicatorRun.status.notin_(_TERMINAL_PHASE_VALUES))
            .order_by(TechnicalIndicatorRun.created_at.desc())
        ).scalars().first()

    def _job(self, run_id: int) -> None:
        provider = self._provider_factory()
        with self._session_factory() as session:
            service.execute_run(session, run_id, provider)


def mark_orphaned_runs_failed(session: Session) -> int:
    """Fail every non-terminal run (called at startup after a restart)."""
    orphans = list(
        session.execute(
            select(TechnicalIndicatorRun).where(
                TechnicalIndicatorRun.status.notin_(_TERMINAL_PHASE_VALUES)
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
default_job_runner = TechnicalIndicatorJobRunner()
