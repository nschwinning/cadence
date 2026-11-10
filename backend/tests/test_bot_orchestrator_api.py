"""API tests for /api/v1/bot-orchestrators."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cadence.api.app import app
from cadence.assets.models import Asset
from cadence.bot_orchestrator.background import get_orchestrator_job_runner
from cadence.bot_orchestrator.models import BotOrchestratorRun
from cadence.config import settings
from cadence.notify.base import Notifier

_BASE = "/api/v1/bot-orchestrators"


class _RecordingRunner:
    """Stands in for the background runner: records submitted run ids."""

    def __init__(self) -> None:
        self.submitted: list[tuple[uuid.UUID, Notifier | None]] = []

    def submit(self, run_id: uuid.UUID, notifier: Notifier | None = None) -> None:
        self.submitted.append((run_id, notifier))


@pytest.fixture
def runner() -> Iterator[_RecordingRunner]:
    recorder = _RecordingRunner()
    app.dependency_overrides[get_orchestrator_job_runner] = lambda: recorder
    try:
        yield recorder
    finally:
        app.dependency_overrides.pop(get_orchestrator_job_runner, None)


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


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"label": "Core", "capital": 10_000.0}
    payload.update(overrides)
    resp = client.post(_BASE, json=payload)
    assert resp.status_code == 201, resp.text
    body: dict[str, object] = resp.json()
    return body


def test_create_and_read(client: TestClient) -> None:
    body = _create(client)

    assert body["status"] == "active"
    assert body["capital"] == 10_000.0
    assert body["free_capital"] == 10_000.0
    assert body["value"] == 10_000.0
    assert body["allocated_capital"] == 0.0
    assert body["max_parallel_bots"] == 3
    assert body["cadence"] == "daily"
    assert body["bots"] == []
    assert body["last_run"] is None

    detail = client.get(f"{_BASE}/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["label"] == "Core"


def test_create_invalid_config_422(client: TestClient) -> None:
    resp = client.post(_BASE, json={"label": "Tiny", "capital": 1_000.0})
    assert resp.status_code == 422


def test_list_hides_archived_unless_requested(client: TestClient) -> None:
    keep = _create(client, label="Keep")
    gone = _create(client, label="Gone")
    client.post(f"{_BASE}/{gone['id']}/stop")
    assert client.post(f"{_BASE}/{gone['id']}/archive").status_code == 200

    listed = client.get(_BASE).json()
    assert [o["id"] for o in listed["items"]] == [keep["id"]]
    everything = client.get(_BASE, params={"include_archived": True}).json()
    assert everything["total"] == 2


def test_archive_active_orchestrator_409(client: TestClient) -> None:
    body = _create(client)
    assert client.post(f"{_BASE}/{body['id']}/archive").status_code == 409


def test_stop_stops_its_bots(
    client: TestClient, db_session: Session, eligible_asset: Asset
) -> None:
    from cadence.bot_orchestrator import service as orchestrator_service
    from cadence.strategy_bots import service as bot_service
    from cadence.strategy_bots.constants import BotOrigin

    body = _create(client)
    orchestrator = orchestrator_service.get_orchestrator(
        db_session, uuid.UUID(str(body["id"]))
    )
    orchestrator.free_capital -= 3_000.0
    bot = bot_service.create_bot_session(
        db_session,
        preset_key="ma_crossover_algo6",
        tickers=["AAPL"],
        initial_capital=3_000.0,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )
    db_session.flush()

    detail = client.get(f"{_BASE}/{body['id']}").json()
    assert detail["active_bots"] == 1
    assert detail["allocated_capital"] == 3_000.0
    assert detail["bots"][0]["preset_name"] == "MA Crossover (Algo 6)"
    assert detail["bots"][0]["tickers"] == ["AAPL"]

    stopped = client.post(f"{_BASE}/{body['id']}/stop").json()

    assert stopped["status"] == "stopped"
    assert stopped["bots"][0]["status"] == "stopped"
    assert stopped["bots"][0]["stop_reason"] == "orchestrator"
    # The bot was flat, so its cash is already back in the pool.
    assert stopped["free_capital"] == 10_000.0
    assert bot.capital_returned_at is not None
    # The bot's own read links back to the orchestrator.
    bot_read = client.get(f"/api/v1/bots/sessions/{bot.id}").json()
    assert bot_read["origin"] == "orchestrator"
    assert bot_read["orchestrator_id"] == body["id"]
    assert bot_read["orchestrator_label"] == "Core"


def test_manual_run_is_queued_and_submitted(
    client: TestClient, runner: _RecordingRunner
) -> None:
    body = _create(client)

    resp = client.post(f"{_BASE}/{body['id']}/runs")

    assert resp.status_code == 202
    run = resp.json()
    assert run["status"] == "queued"
    assert run["trigger"] == "manual"
    assert runner.submitted == [(uuid.UUID(run["id"]), None)]
    # The detail view shows it as the latest run.
    assert client.get(f"{_BASE}/{body['id']}").json()["last_run"]["id"] == run["id"]


def test_manual_run_conflicts(client: TestClient, runner: _RecordingRunner) -> None:
    body = _create(client)
    assert client.post(f"{_BASE}/{body['id']}/runs").status_code == 202
    # A second run while one is queued.
    assert client.post(f"{_BASE}/{body['id']}/runs").status_code == 409

    stopped = _create(client, label="Stopped")
    client.post(f"{_BASE}/{stopped['id']}/stop")
    assert client.post(f"{_BASE}/{stopped['id']}/runs").status_code == 409
    assert len(runner.submitted) == 1


def test_run_due_requires_the_cron_token(
    client: TestClient, runner: _RecordingRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    _create(client)

    assert client.post(f"{_BASE}/run-due").status_code == 403
    assert runner.submitted == []


def test_run_due_starts_only_due_orchestrators(
    client: TestClient,
    db_session: Session,
    runner: _RecordingRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    due = _create(client, label="Daily")
    weekly = _create(client, label="Weekly", cadence="weekly")
    db_session.add(
        BotOrchestratorRun(
            orchestrator_id=uuid.UUID(str(weekly["id"])),
            trigger="scheduled",
            status="succeeded",
            model="gpt-5-mini",
            finished_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    resp = client.post(f"{_BASE}/run-due", headers={"X-Cron-Token": "secret"})

    assert resp.status_code == 200
    assert resp.json() == {"started": 1, "not_due": 1, "already_running": 0}
    assert len(runner.submitted) == 1
    queued = db_session.get(BotOrchestratorRun, runner.submitted[0][0])
    assert queued is not None
    assert str(queued.orchestrator_id) == due["id"]
    assert queued.trigger == "scheduled"
    # Scheduled runs carry the notifier.
    assert runner.submitted[0][1] is not None


def test_run_list_and_detail(client: TestClient, db_session: Session) -> None:
    body = _create(client)
    orchestrator_id = uuid.UUID(str(body["id"]))
    for status_value in ("failed", "succeeded", "partial"):
        db_session.add(
            BotOrchestratorRun(
                orchestrator_id=orchestrator_id,
                trigger="scheduled",
                status=status_value,
                model="gpt-5-mini",
                decision={"market_summary": f"{status_value} day"},
                applied=[],
                rejected=[{"kind": "deploy", "reason": "over budget"}],
            )
        )
        db_session.flush()

    page = client.get(f"{_BASE}/{body['id']}/runs", params={"limit": 2}).json()

    assert page["total"] == 3
    assert len(page["items"]) == 2
    first = page["items"][0]
    assert first["market_summary"] in {"failed day", "succeeded day", "partial day"}
    assert first["rejected"][0]["reason"] == "over budget"

    full = client.get(f"{_BASE}/runs/{first['id']}").json()
    assert full["orchestrator_id"] == body["id"]
    assert full["decision"]["market_summary"] == first["market_summary"]
    assert full["research"] == []


def test_unknown_ids_404(client: TestClient) -> None:
    missing = uuid.uuid4()
    assert client.get(f"{_BASE}/{missing}").status_code == 404
    assert client.post(f"{_BASE}/{missing}/stop").status_code == 404
    assert client.post(f"{_BASE}/{missing}/runs").status_code == 404
    assert client.get(f"{_BASE}/{missing}/runs").status_code == 404
    assert client.get(f"{_BASE}/runs/{missing}").status_code == 404
