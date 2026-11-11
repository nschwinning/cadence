"""Bot tick health: the tick outcome log, per-bot failure state, and the overview summary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_strategy_bots_service import (
    _add_asset,
    _create,
    _OpenableBroker,
    _PerSymbolMarketData,
    _RejectingBuyBroker,
    _up_cross,
)

from cadence.api.app import app
from cadence.broker import get_broker
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.dashboard import service as dashboard_service
from cadence.dashboard.constants import DashboardRange
from cadence.strategy_bots import service
from cadence.strategy_bots.market_data import get_market_data
from cadence.strategy_bots.models import BotSession, BotTickRun

_NOW = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)


class _ClockBroker(StubBroker):
    def __init__(self, *, open_: bool) -> None:
        super().__init__()
        self._open = open_

    def is_market_open(self) -> bool:
        return self._open


def _runs(db: Session) -> list[BotTickRun]:
    db.expire_all()
    return list(db.execute(select(BotTickRun).order_by(BotTickRun.ran_at)).scalars())


@pytest.fixture
def cron_token() -> str:
    original = settings.REBALANCE_CRON_TOKEN
    settings.REBALANCE_CRON_TOKEN = "test-token"
    yield "test-token"
    settings.REBALANCE_CRON_TOKEN = original


def _tick(client: TestClient, token: str) -> object:
    return client.post("/api/v1/bots/tick", headers={"X-Cron-Token": token})


# --- tick outcome log ------------------------------------------------------------------
def test_tick_with_a_failing_bot_is_recorded(
    client: TestClient, db_session: Session, cron_token: str
) -> None:
    broker = _RejectingBuyBroker(reject="NVDA")
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "NVDA")
    _create(db_session, tickers=["AAPL"])
    _create(db_session, tickers=["NVDA"])
    aapl, nvda = broker.get_quote("AAPL").last, broker.get_quote("NVDA").last
    assert aapl is not None and nvda is not None
    app.dependency_overrides[get_broker] = lambda: broker
    app.dependency_overrides[get_market_data] = lambda: _PerSymbolMarketData(
        {"AAPL": _up_cross(aapl), "NVDA": _up_cross(nvda)}
    )

    response = _tick(client, cron_token)

    assert response.status_code == 200  # type: ignore[attr-defined]
    [run] = _runs(db_session)
    assert (run.market_open, run.processed, run.failed, run.error) == (True, 1, 1, None)


def test_market_closed_tick_is_recorded(
    client: TestClient, db_session: Session, cron_token: str
) -> None:
    app.dependency_overrides[get_broker] = lambda: _OpenableBroker(market_open=False)
    app.dependency_overrides[get_market_data] = lambda: _PerSymbolMarketData({})

    _tick(client, cron_token)

    [run] = _runs(db_session)
    assert (run.market_open, run.processed) == (False, 0)


def test_crashed_tick_is_recorded_and_still_fails(
    client: TestClient, db_session: Session, cron_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("reconciliation exploded")

    monkeypatch.setattr(service, "run_tick", _boom)
    app.dependency_overrides[get_broker] = lambda: _OpenableBroker()
    app.dependency_overrides[get_market_data] = lambda: _PerSymbolMarketData({})

    with pytest.raises(RuntimeError):
        _tick(client, cron_token)

    [run] = _runs(db_session)
    assert run.error == "reconciliation exploded"


def test_daily_job_prunes_runs_older_than_a_week(db_session: Session) -> None:
    for days in (8, 6, 0):
        db_session.add(
            BotTickRun(
                ran_at=_NOW - timedelta(days=days),
                market_open=True,
                processed=0,
                skipped=0,
                failed=0,
                flattened=0,
                reconciled=0,
            )
        )
    db_session.flush()

    service.run_bot_snapshots(db_session, broker=StubBroker(), now=_NOW)

    assert [(_NOW - r.ran_at).days for r in _runs(db_session)] == [6, 0]


# --- per-bot failure state ------------------------------------------------------------
def _failing_setup(db: Session) -> tuple[BotSession, _RejectingBuyBroker, _PerSymbolMarketData]:
    broker = _RejectingBuyBroker(reject="NVDA")
    _add_asset(db, "NVDA")
    bot = _create(db, tickers=["NVDA"])
    price = broker.get_quote("NVDA").last
    assert price is not None
    # Bots exist (committed) before any tick in production; a tick's per-bot rollback
    # must not undo the bot's own creation.
    db.commit()
    return bot, broker, _PerSymbolMarketData({"NVDA": _up_cross(price)})


def test_failure_is_recorded_and_counted(db_session: Session) -> None:
    bot, broker, market = _failing_setup(db_session)

    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW + timedelta(minutes=5))

    db_session.refresh(bot)
    assert bot.consecutive_failures == 2
    assert bot.last_failure_at == _NOW + timedelta(minutes=5)
    assert "forbidden" in (bot.last_failure_error or "")


def test_success_clears_the_failure(db_session: Session) -> None:
    bot, broker, market = _failing_setup(db_session)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)
    db_session.refresh(bot)
    assert bot.consecutive_failures == 1

    healthy = _OpenableBroker()
    service.run_tick(
        db_session, broker=healthy, market_data=market, now=_NOW + timedelta(minutes=5)
    )

    db_session.refresh(bot)
    assert (bot.consecutive_failures, bot.last_failure_at, bot.last_failure_error) == (
        0,
        None,
        None,
    )


def test_skipped_bot_keeps_its_failure(db_session: Session) -> None:
    bot, broker, market = _failing_setup(db_session)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)

    # No fresh data next tick: the bot is skipped, neither failing nor succeeding.
    service.run_tick(
        db_session,
        broker=_OpenableBroker(),
        market_data=_PerSymbolMarketData({}),
        now=_NOW + timedelta(minutes=5),
    )

    db_session.refresh(bot)
    assert bot.consecutive_failures == 1


def test_failure_fields_are_in_the_bot_read_model(client: TestClient, db_session: Session) -> None:
    bot, broker, market = _failing_setup(db_session)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)

    body = client.get(f"/api/v1/bots/sessions/{bot.id}").json()

    assert body["consecutive_failures"] == 1
    assert "forbidden" in body["last_failure_error"]
    assert body["last_failure_at"] is not None


# --- overview tick health -------------------------------------------------------------
def _run(db: Session, *, minutes_ago: int, error: str | None = None) -> None:
    db.add(
        BotTickRun(
            ran_at=_NOW - timedelta(minutes=minutes_ago),
            market_open=True,
            processed=3,
            skipped=0,
            failed=0,
            flattened=0,
            reconciled=0,
            error=error,
        )
    )
    db.flush()


def _health(db: Session, *, open_: bool) -> dashboard_service.TickHealth:
    overview = dashboard_service.get_dashboard_overview(
        db,
        range_=DashboardRange.MAX,
        broker=_ClockBroker(open_=open_),
        today=_NOW.date(),
        now=_NOW,
    )
    return overview.tick_health


def test_healthy_ticks(db_session: Session) -> None:
    _run(db_session, minutes_ago=3)

    health = _health(db_session, open_=True)

    assert health.latest is not None and health.latest.processed == 3
    assert (health.stale, health.failing_bots) == (False, [])


def test_ticks_are_stale_when_open_and_old(db_session: Session) -> None:
    _run(db_session, minutes_ago=40)

    assert _health(db_session, open_=True).stale is True


def test_no_ticks_at_all_while_open_is_stale(db_session: Session) -> None:
    health = _health(db_session, open_=True)

    assert (health.latest, health.stale) == (None, True)


def test_closed_market_is_never_stale(db_session: Session) -> None:
    _run(db_session, minutes_ago=600)

    assert _health(db_session, open_=False).stale is False


def test_crashed_latest_tick_carries_its_error(db_session: Session) -> None:
    _run(db_session, minutes_ago=2, error="boom")

    latest = _health(db_session, open_=True).latest
    assert latest is not None and latest.error == "boom"


def test_failing_bots_are_listed(db_session: Session) -> None:
    bot, broker, market = _failing_setup(db_session)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW)
    service.run_tick(db_session, broker=broker, market_data=market, now=_NOW + timedelta(minutes=5))

    [failing] = _health(db_session, open_=True).failing_bots

    assert failing.id == bot.id
    assert failing.display_name == service.bot_display_name(bot)
    assert failing.consecutive_failures == 2
    assert "forbidden" in (failing.last_failure_error or "")


def test_overview_endpoint_serialises_tick_health(client: TestClient, db_session: Session) -> None:
    _run(db_session, minutes_ago=1)
    app.dependency_overrides[get_broker] = lambda: _ClockBroker(open_=False)

    body = client.get("/api/v1/dashboard/overview", params={"range": "Max"}).json()

    health = body["tick_health"]
    assert health["stale"] is False
    assert health["latest"]["processed"] == 3
    assert health["failing_bots"] == []
