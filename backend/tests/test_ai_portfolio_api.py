"""Router tests for /api/v1/ai-portfolio using fakes via dependency override."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent, ManualExecutor

from cadence.ai_portfolio.agent import (
    AIPortfolioBuildResult,
    AIPortfolioStock,
    AIRebalanceResult,
    PositionSide,
)
from cadence.ai_portfolio.background import AIPortfolioJobRunner
from cadence.api.app import app
from cadence.api.routers.ai_portfolio import (
    get_ai_job_runner,
    get_ai_portfolio_agent,
)
from cadence.broker import get_broker
from cadence.broker.stub import StubBroker
from cadence.config import settings


def _build_result() -> AIPortfolioBuildResult:
    return AIPortfolioBuildResult(
        portfolio_name="AI Growth",
        stocks=[
            AIPortfolioStock(
                ticker="AAPL",
                company_name="Apple",
                side=PositionSide.LONG,
                allocation_pct=0.5,
                investment_thesis="strong",
                confidence=0.8,
            ),
            AIPortfolioStock(
                ticker="MSFT",
                company_name="Microsoft",
                side=PositionSide.LONG,
                allocation_pct=0.5,
                investment_thesis="cloud",
                confidence=0.9,
            ),
        ],
        overall_thesis="tech",
        risk_assessment="risk",
    )


def _rebalance_result() -> AIRebalanceResult:
    return AIRebalanceResult(
        evaluation_summary="steady",
        existing_holdings=[],
        portfolio_health="healthy",
    )


def _wire(
    db_session: Session,
    executor: ManualExecutor,
    *,
    broker: StubBroker | None = None,
    agent: FakeAIPortfolioAgent | None = None,
) -> tuple[AIPortfolioJobRunner, StubBroker]:
    @contextmanager
    def factory() -> Iterator[Session]:
        yield db_session

    shared_broker = broker or StubBroker()
    fake_agent = agent or FakeAIPortfolioAgent(
        build_result=_build_result(), rebalance_result=_rebalance_result()
    )
    runner = AIPortfolioJobRunner(session_factory=factory, executor=executor)
    app.dependency_overrides[get_ai_portfolio_agent] = lambda: fake_agent
    app.dependency_overrides[get_broker] = lambda: shared_broker
    app.dependency_overrides[get_ai_job_runner] = lambda: runner
    return runner, shared_broker


def test_build_returns_202_and_status_poll(
    client: TestClient, db_session: Session
) -> None:
    executor = ManualExecutor()
    _wire(db_session, executor)

    resp = client.post(
        "/api/v1/ai-portfolio/build",
        json={"tickers": ["AAPL", "MSFT"], "allocated_capital": 100000},
    )
    assert resp.status_code == 202
    event_id = resp.json()["event_id"]
    assert resp.json()["status"] == "queued"

    # Drive the deferred job, then poll for the terminal status.
    executor.run_pending()
    polled = client.get(f"/api/v1/ai-portfolio/build/status/{event_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "succeeded"
    assert body["session_id"] is not None
    assert body["portfolio_id"] is not None


def test_build_rejects_too_few_tickers(
    client: TestClient, db_session: Session
) -> None:
    _wire(db_session, ManualExecutor())
    resp = client.post(
        "/api/v1/ai-portfolio/build", json={"tickers": ["AAPL"]}
    )
    # min_length=2 on the request schema -> 422 at validation.
    assert resp.status_code == 422


def test_build_status_unknown_event_404(
    client: TestClient, db_session: Session
) -> None:
    _wire(db_session, ManualExecutor())
    resp = client.get(
        "/api/v1/ai-portfolio/build/status/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def _build_session(client: TestClient, executor: ManualExecutor) -> str:
    """Build a session synchronously and return its id."""
    resp = client.post(
        "/api/v1/ai-portfolio/build",
        json={
            "tickers": ["AAPL", "MSFT"],
            "allocated_capital": 100000,
            "daily_rebalancing": True,
        },
    )
    event_id = resp.json()["event_id"]
    executor.run_pending()
    status = client.get(f"/api/v1/ai-portfolio/build/status/{event_id}").json()
    return status["session_id"]


def test_session_rebalance_and_events_listing(
    client: TestClient, db_session: Session
) -> None:
    executor = ManualExecutor()
    _wire(db_session, executor)
    session_id = _build_session(client, executor)

    resp = client.post(f"/api/v1/ai-portfolio/sessions/{session_id}/rebalance")
    assert resp.status_code == 200
    assert resp.json()["started"] is True
    executor.run_pending()

    events = client.get(f"/api/v1/ai-portfolio/sessions/{session_id}/events")
    assert events.status_code == 200
    types = {e["event_type"] for e in events.json()}
    assert "rebalance" in types


def test_session_rebalance_skips_when_already_running(
    client: TestClient, db_session: Session
) -> None:
    executor = ManualExecutor()  # deferred: first rebalance stays queued/inflight
    _wire(db_session, executor)
    session_id = _build_session(client, executor)

    first = client.post(f"/api/v1/ai-portfolio/sessions/{session_id}/rebalance")
    assert first.json()["started"] is True
    second = client.post(f"/api/v1/ai-portfolio/sessions/{session_id}/rebalance")
    assert second.json()["started"] is False
    assert second.json()["event_id"] == first.json()["event_id"]


def test_session_rebalance_non_eligible_rejected(
    client: TestClient, db_session: Session
) -> None:
    from cadence.paper_trading import service as paper_service
    from cadence.portfolios import service as portfolios_service

    _wire(db_session, ManualExecutor())
    # A non-AI session is not eligible for rebalancing.
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Manual", stocks=["AAPL"]
    )
    session_row = paper_service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
    resp = client.post(
        f"/api/v1/ai-portfolio/sessions/{session_row.id}/rebalance"
    )
    assert resp.status_code == 409


def test_session_rebalance_unknown_session_404(
    client: TestClient, db_session: Session
) -> None:
    _wire(db_session, ManualExecutor())
    resp = client.post(
        "/api/v1/ai-portfolio/sessions/"
        "00000000-0000-0000-0000-000000000000/rebalance"
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Daily fan-out + cron token guard
# --------------------------------------------------------------------------- #


def test_rebalance_daily_rejects_without_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    _wire(db_session, ManualExecutor())
    resp = client.post("/api/v1/ai-portfolio/rebalance-daily")
    assert resp.status_code == 403


def test_rebalance_daily_rejects_wrong_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    _wire(db_session, ManualExecutor())
    resp = client.post(
        "/api/v1/ai-portfolio/rebalance-daily",
        headers={"X-Cron-Token": "wrong"},
    )
    assert resp.status_code == 403


def test_rebalance_daily_empty_config_rejects_all(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "")
    _wire(db_session, ManualExecutor())
    resp = client.post(
        "/api/v1/ai-portfolio/rebalance-daily",
        headers={"X-Cron-Token": ""},
    )
    assert resp.status_code == 403


def test_rebalance_daily_fans_out_to_enrolled_sessions(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    executor = ManualExecutor(run_immediately=True)
    _wire(db_session, executor)
    session_id = _build_session(client, executor)

    resp = client.post(
        "/api/v1/ai-portfolio/rebalance-daily",
        headers={"X-Cron-Token": "secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions_triggered"] == 1
    assert session_id in body["session_ids"]
