"""Tests for background execution: non-blocking start, orphan/dead reaping."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from sqlalchemy.orm import Session
from tests.fakes import (
    FakeMarketDataProvider,
    FakeRecommenderAgent,
    ManualExecutor,
)

from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.recommendations import service
from cadence.recommendations.agent import RecommendationCandidate
from cadence.recommendations.background import (
    RecommendationJobRunner,
    mark_orphaned_runs_failed,
)
from cadence.recommendations.constants import RunPhase


def _provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Test Co",
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _runner(db_session: Session, executor: ManualExecutor) -> RecommendationJobRunner:
    @contextmanager
    def factory() -> Iterator[Session]:
        # Reuse the test session; do not close it (the fixture owns its lifecycle).
        yield db_session

    return RecommendationJobRunner(session_factory=factory, executor=executor)


def test_start_run_returns_before_completion(db_session: Session) -> None:
    executor = ManualExecutor()
    runner = _runner(db_session, executor)
    agent = FakeRecommenderAgent(
        candidates=[RecommendationCandidate(ticker="AAA", rationale="x")],
        tool_call_count=1,
    )

    run, started = runner.start_run(
        db_session, count=1, categories=["stock"], agent=agent, provider=_provider()
    )

    # The job has been submitted but not yet run: still queued.
    assert started is True
    assert run.status == RunPhase.QUEUED.value

    executor.run_pending()

    completed = runner.status(db_session, run.id)
    assert completed.status == RunPhase.COMPLETED.value


def test_single_run_guard_returns_inflight(db_session: Session) -> None:
    executor = ManualExecutor()  # jobs stay pending -> first run stays in flight
    runner = _runner(db_session, executor)
    agent = FakeRecommenderAgent(candidates=[], tool_call_count=0)

    first, first_started = runner.start_run(
        db_session, count=1, categories=["stock"], agent=agent, provider=_provider()
    )
    second, second_started = runner.start_run(
        db_session, count=2, categories=["etf"], agent=agent, provider=_provider()
    )

    assert first_started is True
    assert second_started is False
    assert second.id == first.id  # in-flight run returned, no new run created


def test_status_reaps_dead_worker(db_session: Session) -> None:
    # A queued run whose worker dies before writing a terminal phase must be
    # reaped (reported failed) on the next status read.
    run_id = service.create_run(db_session, count=1, categories=["stock"])

    @contextmanager
    def broken_factory() -> Iterator[Session]:
        raise RuntimeError("session boom")
        yield db_session  # pragma: no cover

    crashing = RecommendationJobRunner(
        session_factory=broken_factory, executor=ManualExecutor(run_immediately=True)
    )
    future = crashing._executor.submit(  # type: ignore[attr-defined]
        crashing._job,
        run_id,
        FakeRecommenderAgent(),
        _provider(),
    )
    crashing._active[run_id] = future

    reaped = crashing.status(db_session, run_id)
    assert reaped.status == RunPhase.FAILED.value
    assert reaped.error is not None and "boom" in reaped.error


def test_mark_orphaned_runs_failed(db_session: Session) -> None:
    queued = service.create_run(db_session, count=1, categories=["stock"])
    searching_id = service.create_run(db_session, count=1, categories=["stock"])
    searching = service.get_run(db_session, searching_id)
    searching.status = RunPhase.SEARCHING.value
    db_session.commit()

    count = mark_orphaned_runs_failed(db_session)

    assert count >= 2
    assert service.get_run(db_session, queued).status == RunPhase.FAILED.value
    reaped = service.get_run(db_session, searching_id)
    assert reaped.status == RunPhase.FAILED.value
    assert reaped.error == "orphaned by restart"
