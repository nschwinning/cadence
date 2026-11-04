"""Router tests for the strategy-bot API (lifecycle, reads, cron jobs)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import RecordingNotifier

from cadence.api.app import app
from cadence.assets.models import Asset
from cadence.broker.models import OrderSide
from cadence.config import settings
from cadence.notify import get_notifier
from cadence.strategy_bots.market_data import StubMarketData, get_market_data
from cadence.strategy_bots.models import BotTrade, BotValuePoint, BotValueSnapshot


@pytest.fixture
def eligible_asset(db_session: Session) -> Asset:
    asset = Asset(
        ticker="AAPL",
        name="Apple",
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()
    return asset


@pytest.fixture
def stub_market_data() -> Iterator[None]:
    """Serve deterministic flat/fresh bars to the tick endpoint."""
    app.dependency_overrides[get_market_data] = lambda: StubMarketData()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_market_data, None)


@pytest.fixture
def recording_notifier() -> Iterator[RecordingNotifier]:
    """Override the notifier DI so tests can assert it is threaded into the jobs."""
    notifier = RecordingNotifier()
    app.dependency_overrides[get_notifier] = lambda: notifier
    try:
        yield notifier
    finally:
        app.dependency_overrides.pop(get_notifier, None)


def _create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_key": "ma_crossover",
        "tickers": ["AAPL"],
        "initial_capital": 100_000.0,
        "benchmark": "SP500",
        "strategy_params": {"fast_period": 2, "slow_period": 3},
    }
    payload.update(overrides)
    return payload


# Lifecycle ---------------------------------------------------------------
def test_create_bot_session(client: TestClient, eligible_asset: Asset) -> None:
    resp = client.post("/api/v1/bots/sessions", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert [s["ticker"] for s in body["symbols"]] == ["AAPL"]
    assert body["positions"] == []
    assert body["cash"] == 100_000.0
    assert body["sizing_method"] == "atr_risk"
    assert body["status"] == "active"
    assert body["strategy_key"] == "ma_crossover"


def test_create_bot_session_whole_universe(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_create_payload(tickers=None, whole_universe=True),
    )
    assert resp.status_code == 201
    assert {s["ticker"] for s in resp.json()["symbols"]} == {"AAPL"}


def test_create_rejects_unknown_sizing_method(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_create_payload(sizing_method="moon_math"),
    )
    assert resp.status_code == 422


def test_create_rejects_unknown_strategy(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions", json=_create_payload(strategy_key="nope")
    )
    assert resp.status_code == 422


def test_create_rejects_ineligible_asset(client: TestClient) -> None:
    # No asset seeded → ticker not in the eligible universe.
    resp = client.post("/api/v1/bots/sessions", json=_create_payload())
    assert resp.status_code == 422


def test_list_and_get_session(
    client: TestClient, eligible_asset: Asset
) -> None:
    created = client.post(
        "/api/v1/bots/sessions", json=_create_payload()
    ).json()

    listed = client.get("/api/v1/bots/sessions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    # Each listed session carries its current value (cost-basis before any snapshot).
    assert listed.json()["items"][0]["current_value"] == 100_000.0

    detail = client.get(f"/api/v1/bots/sessions/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert detail.json()["current_value"] == 100_000.0


def test_get_unknown_session_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def test_stop_then_archive(client: TestClient, eligible_asset: Asset) -> None:
    created = client.post(
        "/api/v1/bots/sessions", json=_create_payload()
    ).json()
    sid = created["id"]

    stopped = client.post(f"/api/v1/bots/sessions/{sid}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    archived = client.post(f"/api/v1/bots/sessions/{sid}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_archive_active_conflicts(
    client: TestClient, eligible_asset: Asset
) -> None:
    created = client.post(
        "/api/v1/bots/sessions", json=_create_payload()
    ).json()
    resp = client.post(f"/api/v1/bots/sessions/{created['id']}/archive")
    assert resp.status_code == 409


# Reads -------------------------------------------------------------------
def test_kpis_value_history_and_trades(
    client: TestClient, eligible_asset: Asset
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]

    kpis = client.get(f"/api/v1/bots/sessions/{sid}/kpis")
    assert kpis.status_code == 200
    assert kpis.json()["current_value"] == 100_000.0
    # Available cash is surfaced on the KPIs (all cash before any position opens).
    assert kpis.json()["cash"] == 100_000.0
    # Sharpe is serialized; null until the session has enough snapshot history.
    assert kpis.json()["sharpe_ratio"] is None
    # No closed round-trip yet → best/worst trade null.
    assert kpis.json()["best_trade"] is None
    assert kpis.json()["worst_trade"] is None

    history = client.get(f"/api/v1/bots/sessions/{sid}/value-history")
    assert history.status_code == 200
    assert history.json()["total"] == 0

    trades = client.get(f"/api/v1/bots/sessions/{sid}/trades")
    assert trades.status_code == 200
    assert trades.json()["total"] == 0


def test_kpis_report_best_and_worst_closed_trade(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    # One closed round-trip: buy 10 @ 50, sell 10 @ 56 → +60 realized.
    db_session.add_all(
        [
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.BUY.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=50.0,
                fees=0.0,
                created_at=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
            ),
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.SELL.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=56.0,
                fees=0.0,
                created_at=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.flush()

    body = client.get(f"/api/v1/bots/sessions/{sid}/kpis").json()
    assert body["best_trade"] == {"ticker": "AAPL", "realised_pnl": 60.0}
    assert body["worst_trade"] == {"ticker": "AAPL", "realised_pnl": 60.0}


def test_trades_pagination(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    for minute in range(3):
        db_session.add(
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.BUY.value,
                ticker="AAPL",
                quantity=1.0,
                filled_price=10.0,
                fees=0.0,
                created_at=datetime(2026, 1, 6, 9, minute, tzinfo=UTC),
            )
        )
    db_session.flush()

    # Default page: full total, bounded items, most-recent-first.
    first = client.get(f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 2})
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    # Second page via offset.
    second = client.get(
        f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 2, "offset": 2}
    )
    assert second.json()["total"] == 3
    assert len(second.json()["items"]) == 1


def test_trades_pagination_rejects_bad_params(
    client: TestClient, eligible_asset: Asset
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 101}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"offset": -1}
        ).status_code
        == 422
    )


def test_trades_unknown_session_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000/trades"
    )
    assert resp.status_code == 404


def test_value_history_honours_resolution(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    bot_id = uuid.UUID(sid)
    # Two intraday points in one hour; one daily snapshot.
    db_session.add_all(
        [
            BotValuePoint(
                bot_session_id=bot_id,
                captured_at=datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
                total_value=100.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
            BotValuePoint(
                bot_session_id=bot_id,
                captured_at=datetime(2026, 1, 6, 15, 30, tzinfo=UTC),
                total_value=105.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
            BotValueSnapshot(
                bot_session_id=bot_id,
                snapshot_date=date(2026, 1, 6),
                total_value=105.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
        ]
    )
    db_session.flush()

    five = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history", params={"resolution": "5min"}
    )
    assert five.status_code == 200
    assert five.json()["resolution"] == "5min"
    assert len(five.json()["items"]) == 2
    assert "timestamp" in five.json()["items"][0]

    hourly = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history", params={"resolution": "hourly"}
    )
    assert len(hourly.json()["items"]) == 1
    assert hourly.json()["items"][0]["total_value"] == 105.0

    # Default resolution is daily (reads the snapshot curve, not the points).
    default = client.get(f"/api/v1/bots/sessions/{sid}/value-history")
    assert default.json()["resolution"] == "daily"
    assert len(default.json()["items"]) == 1


def test_value_history_rejects_unknown_resolution(
    client: TestClient, eligible_asset: Asset
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    resp = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history",
        params={"resolution": "weekly"},
    )
    assert resp.status_code == 422


def test_value_history_unknown_session_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000/value-history"
    )
    assert resp.status_code == 404


def test_list_strategies(client: TestClient) -> None:
    resp = client.get("/api/v1/bots/strategies")
    assert resp.status_code == 200
    keys = {entry["key"] for entry in resp.json()}
    assert "ma_crossover" in keys


# Cron-guarded jobs -------------------------------------------------------
def test_tick_rejects_without_token(
    client: TestClient, stub_market_data: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post("/api/v1/bots/tick")
    assert resp.status_code == 403


def test_tick_authorized(
    client: TestClient,
    eligible_asset: Asset,
    stub_market_data: None,
    recording_notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    client.post("/api/v1/bots/sessions", json=_create_payload())

    resp = client.post(
        "/api/v1/bots/tick", headers={"X-Cron-Token": "secret"}
    )
    assert resp.status_code == 200
    assert resp.json()["market_open"] is True
    # Notifier is threaded (no kill-switch trips here, so nothing is pushed).
    assert recording_notifier.sent == []


def test_snapshot_daily_rejects_without_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    resp = client.post("/api/v1/bots/snapshot-daily")
    assert resp.status_code == 403


def test_snapshot_daily_authorized(
    client: TestClient,
    eligible_asset: Asset,
    recording_notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    client.post("/api/v1/bots/sessions", json=_create_payload())

    resp = client.post(
        "/api/v1/bots/snapshot-daily", headers={"X-Cron-Token": "secret"}
    )
    assert resp.status_code == 200
    assert resp.json()["snapshots"] == 1
    # Notifier is threaded: one daily-summary push for the single active bot.
    assert len(recording_notifier.sent) == 1
    assert "daily P&L" in recording_notifier.sent[0][1]
