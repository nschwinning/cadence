"""Tests for orchestrator dashboard rows (``kind='orchestrator'``)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.bot_orchestrator import dashboard
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.bot_orchestrator.models import BotOrchestrator, BotOrchestratorSnapshot
from cadence.broker.stub import StubBroker
from cadence.dashboard import service as dashboard_service
from cadence.dashboard.constants import DashboardRange
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin
from cadence.strategy_bots.models import BotSession, BotValueSnapshot

_TODAY = date(2026, 6, 15)
_NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _asset(db: Session, ticker: str) -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db.add(asset)
    db.flush()
    return asset


def _orchestrator(db: Session) -> BotOrchestrator:
    return orchestrator_service.create_orchestrator(
        db, label="First Orchestrator", capital=10_000.0
    )


def _deploy(
    db: Session, orchestrator: BotOrchestrator, ticker: str, capital: float
) -> BotSession:
    orchestrator.free_capital -= capital
    return bot_service.create_bot_session(
        db,
        preset_key="donchian_turtle_algo25",
        tickers=[ticker],
        initial_capital=capital,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )


def _bot_snapshot(db: Session, bot: BotSession, value: float, unrealised: float) -> None:
    db.add(
        BotValueSnapshot(
            session=bot,
            snapshot_date=_TODAY,
            total_value=value,
            realised_pnl=0.0,
            unrealised_pnl=unrealised,
        )
    )
    db.flush()


def _snapshot(db: Session, orchestrator: BotOrchestrator, on: date, value: float) -> None:
    db.add(
        BotOrchestratorSnapshot(
            orchestrator_id=orchestrator.id,
            snapshot_date=on,
            value=value,
            free_capital=0.0,
            allocated_capital=0.0,
            active_bots=0,
        )
    )
    db.flush()


def test_row_covers_free_capital_and_bots(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    bot = _deploy(db_session, orchestrator, "MSFT", 3_300.0)
    _bot_snapshot(db_session, bot, 3_350.0, unrealised=50.0)

    row = dashboard.dashboard_performance(
        db_session, orchestrator, range_=DashboardRange.MAX, today=_TODAY
    )

    assert row.kind == "orchestrator"
    assert row.id == orchestrator.id
    assert row.label == "First Orchestrator"
    assert row.allocated_capital == 10_000.0
    assert row.current_value == pytest.approx(6_700.0 + 3_350.0)
    assert row.unrealised_pnl == pytest.approx(50.0)
    assert [(c.amount) for c in row.contributions] == [10_000.0]
    assert row.pnl == pytest.approx(50.0)


def test_recycled_capital_is_not_a_new_contribution(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    first = _deploy(db_session, orchestrator, "MSFT", 3_000.0)
    bot_service.stop_bot_session(db_session, first.id)
    orchestrator_service.settle_returned_capital(db_session, orchestrator)
    _deploy(db_session, orchestrator, "AAPL", 3_000.0)

    row = dashboard.dashboard_performance(
        db_session, orchestrator, range_=DashboardRange.MAX, today=_TODAY
    )

    assert len(row.contributions) == 1
    assert row.contributions[0].amount == 10_000.0
    assert row.current_value == pytest.approx(10_000.0)


def test_series_falls_back_to_one_live_point_without_snapshots(
    db_session: Session,
) -> None:
    orchestrator = _orchestrator(db_session)

    row = dashboard.dashboard_performance(
        db_session, orchestrator, range_=DashboardRange.MAX, today=_TODAY
    )

    assert [(p.date, p.value) for p in row.points] == [(_TODAY, 10_000.0)]
    assert row.contributions[0].effective_date == _TODAY


def test_series_windows_to_the_range_and_pnl_uses_range_start(
    db_session: Session,
) -> None:
    orchestrator = _orchestrator(db_session)
    _snapshot(db_session, orchestrator, _TODAY - timedelta(days=40), 9_800.0)
    _snapshot(db_session, orchestrator, _TODAY - timedelta(days=35), 9_900.0)
    _snapshot(db_session, orchestrator, _TODAY - timedelta(days=10), 10_100.0)

    row = dashboard.dashboard_performance(
        db_session, orchestrator, range_=DashboardRange.MONTH, today=_TODAY
    )

    # Only the snapshot inside the last month is plotted...
    assert [p.date for p in row.points] == [_TODAY - timedelta(days=10)]
    # ...and range P&L is measured from the latest snapshot on/before the start.
    assert row.pnl == pytest.approx(10_000.0 - 9_900.0)
    # The single contribution is anchored at the first snapshot.
    assert row.contributions[0].effective_date == _TODAY - timedelta(days=40)


def test_realised_and_fees_sum_over_all_its_bots(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    _asset(db_session, "AAPL")
    orchestrator = _orchestrator(db_session)
    finished = _deploy(db_session, orchestrator, "MSFT", 2_000.0)
    finished.realised_pnl = 120.0
    finished.total_fees = 1.5
    bot_service.stop_bot_session(db_session, finished.id)
    active = _deploy(db_session, orchestrator, "AAPL", 2_000.0)
    active.realised_pnl = -20.0
    active.total_fees = 0.5
    db_session.flush()

    row = dashboard.dashboard_performance(
        db_session, orchestrator, range_=DashboardRange.MAX, today=_TODAY
    )

    assert row.realised_pnl == pytest.approx(100.0)
    assert row.fees == pytest.approx(2.0)


def test_stopped_orchestrators_have_no_row(db_session: Session) -> None:
    keep = _orchestrator(db_session)
    gone = orchestrator_service.create_orchestrator(
        db_session, label="Retired", capital=5_000.0
    )
    orchestrator_service.stop_orchestrator(db_session, gone.id)

    rows = dashboard.dashboard_performances(
        db_session, range_=DashboardRange.MAX, today=_TODAY
    )

    assert [r.id for r in rows] == [keep.id]


def test_overview_shows_the_orchestrator_not_its_bot(db_session: Session) -> None:
    _asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    bot = _deploy(db_session, orchestrator, "MSFT", 3_000.0)

    overview = dashboard_service.get_dashboard_overview(
        db_session,
        range_=DashboardRange.MAX,
        broker=StubBroker(),
        today=_TODAY,
        now=_NOW,
    )

    ids = {(s.id, s.kind) for s in overview.sessions}
    assert (orchestrator.id, "orchestrator") in ids
    assert bot.id not in {s.id for s in overview.sessions}


def test_overview_endpoint_serialises_the_orchestrator_kind(
    client: TestClient, db_session: Session
) -> None:
    orchestrator = _orchestrator(db_session)

    body = client.get("/api/v1/dashboard/overview", params={"range": "Max"}).json()

    row = next(s for s in body["sessions"] if s["id"] == str(orchestrator.id))
    assert row["kind"] == "orchestrator"
    assert row["label"] == "First Orchestrator"
    assert row["current_value"] == 10_000.0
