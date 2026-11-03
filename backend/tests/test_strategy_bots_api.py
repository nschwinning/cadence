"""Router tests for the strategy-bot API (lifecycle, reads, cron jobs)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import RecordingNotifier

from cadence.api.app import app
from cadence.assets.models import Asset
from cadence.config import settings
from cadence.notify import get_notifier
from cadence.strategy_bots.market_data import StubMarketData, get_market_data


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

    detail = client.get(f"/api/v1/bots/sessions/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]


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
    # Sharpe is serialized; null until the session has enough snapshot history.
    assert kpis.json()["sharpe_ratio"] is None

    history = client.get(f"/api/v1/bots/sessions/{sid}/value-history")
    assert history.status_code == 200
    assert history.json()["total"] == 0

    trades = client.get(f"/api/v1/bots/sessions/{sid}/trades")
    assert trades.status_code == 200
    assert trades.json()["total"] == 0


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
