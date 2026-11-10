"""In-process background execution for orchestrator decision runs.

Runs execute on a dedicated single-worker thread pool, separate from the AI-portfolio
runner, so decision runs never queue behind (or ahead of) portfolio rebalances. The
endpoint creates and commits a queued run, then submits its id; the job opens its own
session and executes it. Runs left queued or running by a restart are failed at
startup (:func:`cleanup_orphaned_runs_on_startup`).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, cast

from sqlalchemy.orm import Session

from cadence.bot_orchestrator import runs
from cadence.bot_orchestrator.agent import OpenAIOrchestratorAgent, OrchestratorAgent
from cadence.broker import get_broker
from cadence.broker.base import Broker
from cadence.database import SessionLocal
from cadence.notify.base import Notifier

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]


@contextmanager
def _open_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


class _Executor(Protocol):
    def submit(self, fn: Callable[..., object], /, *args: object) -> Future[None]: ...


class OrchestratorJobRunner:
    """Owns the single worker that executes queued decision runs."""

    def __init__(
        self,
        session_factory: SessionFactory = _open_session,
        agent_factory: Callable[[], OrchestratorAgent] = OpenAIOrchestratorAgent,
        broker_factory: Callable[[], Broker] = get_broker,
        executor: _Executor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agent_factory = agent_factory
        self._broker_factory = broker_factory
        self._executor: _Executor = executor or cast(
            "_Executor",
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="cadence-orchestrator"),
        )

    def submit(self, run_id: uuid.UUID, notifier: Notifier | None = None) -> None:
        """Execute a committed, queued run in the background."""
        self._executor.submit(self._job, run_id, notifier)

    def _job(self, run_id: uuid.UUID, notifier: Notifier | None) -> None:
        try:
            with self._session_factory() as session:
                runs.execute_run(
                    session,
                    run_id,
                    agent=self._agent_factory(),
                    broker=self._broker_factory(),
                    notifier=notifier,
                )
        except Exception:  # pragma: no cover - execute_run records its own failures
            logger.exception("orchestrator job for run %s crashed", run_id)


_runner: OrchestratorJobRunner | None = None


def get_orchestrator_job_runner() -> OrchestratorJobRunner:
    """The process-wide runner (a FastAPI dependency; tests override it)."""
    global _runner
    if _runner is None:
        _runner = OrchestratorJobRunner()
    return _runner


def cleanup_orphaned_runs_on_startup() -> int:
    """Fail any runs a previous process left queued or running."""
    with _open_session() as session:
        return runs.fail_orphaned_runs(session)
