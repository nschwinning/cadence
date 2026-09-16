"""Router tests for /api/v1/ai-portfolio using fakes via dependency override.

Builds now allocate over the whole asset universe (no ticker list in the
request), so each build test seeds a universe first and overrides the
market-data provider dependency with an in-memory fake (no network).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent, FakeMarketDataProvider, ManualExecutor

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
from cadence.api.routers.assets import get_market_data_provider
from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.broker import get_broker
from cadence.broker.stub import StubBroker
from cadence.config import settings


def _provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Co",
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
            sector_key="technology",
            country="Germany",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _seed_universe(db_session: Session, provider: FakeMarketDataProvider) -> None:
    for ticker in ("AAPL", "MSFT"):
        assets_service.add_asset(db_session, ticker, provider, StubBroker())


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
        target_allocations=[],
        portfolio_health="healthy",
    )


def _wire(
    db_session: Session,
    executor: ManualExecutor,
    *,
    broker: StubBroker | None = None,
    agent: FakeAIPortfolioAgent | None = None,
    provider: FakeMarketDataProvider | None = None,
) -> tuple[AIPortfolioJobRunner, StubBroker]:
    @contextmanager
    def factory() -> Iterator[Session]:
        yield db_session

    shared_broker = broker or StubBroker()
    fake_agent = agent or FakeAIPortfolioAgent(
        build_result=_build_result(), rebalance_result=_rebalance_result()
    )
    fake_provider = provider or _provider()
    runner = AIPortfolioJobRunner(session_factory=factory, executor=executor)
    app.dependency_overrides[get_ai_portfolio_agent] = lambda: fake_agent
    app.dependency_overrides[get_broker] = lambda: shared_broker
    app.dependency_overrides[get_market_data_provider] = lambda: fake_provider
    app.dependency_overrides[get_ai_job_runner] = lambda: runner
    return runner, shared_broker


def test_build_returns_202_and_status_poll(
    client: TestClient, db_session: Session
) -> None:
    executor = ManualExecutor()
    _seed_universe(db_session, _provider())
    _wire(db_session, executor)

    resp = client.post(
        "/api/v1/ai-portfolio/build",
        json={"allocated_capital": 100000},
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


def test_build_rejects_empty_universe(client: TestClient, db_session: Session) -> None:
    # No assets seeded -> the universe is empty -> the build is rejected (422).
    _wire(db_session, ManualExecutor())
    resp = client.post("/api/v1/ai-portfolio/build", json={"allocated_capital": 100000})
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
    _seed_universe(db_session, _provider())
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
    _seed_universe(db_session, _provider())
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
# Runs history + detail
# --------------------------------------------------------------------------- #


def test_list_runs_and_detail(client: TestClient, db_session: Session) -> None:
    executor = ManualExecutor()
    _seed_universe(db_session, _provider())
    # Give the agent research so the persisted transcript is exercised end-to-end.
    agent = FakeAIPortfolioAgent(
        build_result=_build_result(),
        rebalance_result=_rebalance_result(),
        research_queries=["AAPL earnings"],
    )
    _wire(db_session, executor, agent=agent)
    _build_session(client, executor)

    # The runs list returns the build event with its research count.
    listing = client.get("/api/v1/ai-portfolio/runs")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    run = body["items"][0]
    assert run["event_type"] == "build"
    assert run["research"] == [
        {
            "query": "AAPL earnings",
            "results": {"organic_results": [{"title": "result for AAPL earnings"}]},
            "error": None,
        }
    ]

    # The detail endpoint returns the run with the trades it opened.
    detail = client.get(f"/api/v1/ai-portfolio/runs/{run['id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["event"]["id"] == run["id"]
    opened = {t["ticker"] for t in detail_body["trades"]}
    assert opened == {"AAPL", "MSFT"}
    assert all(t["ai_portfolio_event_id"] == run["id"] for t in detail_body["trades"])
    assert detail_body["closed_positions"] == []

    # Filtering by a non-matching type yields an empty page.
    rebalances = client.get("/api/v1/ai-portfolio/runs", params={"event_type": "rebalance"})
    assert rebalances.status_code == 200
    assert rebalances.json()["total"] == 0


def test_run_detail_unknown_event_404(client: TestClient, db_session: Session) -> None:
    _wire(db_session, ManualExecutor())
    resp = client.get(
        "/api/v1/ai-portfolio/runs/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Close portfolio
# --------------------------------------------------------------------------- #


def test_close_session_liquidates_and_stops(
    client: TestClient, db_session: Session
) -> None:
    executor = ManualExecutor()
    _seed_universe(db_session, _provider())
    _wire(db_session, executor)
    session_id = _build_session(client, executor)

    resp = client.post(f"/api/v1/ai-portfolio/sessions/{session_id}/close")
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"]["event_type"] == "close"
    assert body["event"]["status"] == "succeeded"
    # Every held ticker was closed and linked to the close event.
    assert {c["ticker"] for c in body["closed_positions"]} == {"AAPL", "MSFT"}
    assert all(
        c["ai_portfolio_event_id"] == body["event"]["id"]
        for c in body["closed_positions"]
    )
    assert {t["ticker"] for t in body["trades"]} == {"AAPL", "MSFT"}

    # The session is now stopped: closing again is rejected as non-eligible.
    again = client.post(f"/api/v1/ai-portfolio/sessions/{session_id}/close")
    assert again.status_code == 409


def test_close_unknown_session_404(client: TestClient, db_session: Session) -> None:
    _wire(db_session, ManualExecutor())
    resp = client.post(
        "/api/v1/ai-portfolio/sessions/"
        "00000000-0000-0000-0000-000000000000/close"
    )
    assert resp.status_code == 404


def test_close_non_eligible_session_rejected(
    client: TestClient, db_session: Session
) -> None:
    from cadence.paper_trading import service as paper_service
    from cadence.portfolios import service as portfolios_service

    _wire(db_session, ManualExecutor())
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Manual", stocks=["AAPL"]
    )
    session_row = paper_service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
    resp = client.post(f"/api/v1/ai-portfolio/sessions/{session_row.id}/close")
    assert resp.status_code == 409


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
    _seed_universe(db_session, _provider())
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


def test_snapshot_daily_rejects_without_token(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    _wire(db_session, ManualExecutor())
    resp = client.post("/api/v1/ai-portfolio/snapshot-daily")
    assert resp.status_code == 403


def test_snapshot_daily_fans_out_to_active_ai_sessions(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    executor = ManualExecutor(run_immediately=True)
    _seed_universe(db_session, _provider())
    _wire(db_session, executor)
    session_id = _build_session(client, executor)

    resp = client.post(
        "/api/v1/ai-portfolio/snapshot-daily",
        headers={"X-Cron-Token": "secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions_snapshotted"] == 1
    assert session_id in body["session_ids"]
