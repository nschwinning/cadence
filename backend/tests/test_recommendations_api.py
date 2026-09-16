"""Router tests for /api/v1/recommendations using fakes via dependency override."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import (
    FakeMarketDataProvider,
    FakeRecommenderAgent,
    ManualExecutor,
)

from cadence.api.app import app
from cadence.api.routers.recommendations import (
    get_job_runner,
    get_market_data_provider,
    get_recommender_agent,
)
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.recommendations.agent import RecommendationCandidate
from cadence.recommendations.background import RecommendationJobRunner


def _provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Test Co",
            exchange="XETRA",
            currency="USD",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _wire(
    client: TestClient,
    db_session: Session,
    agent: FakeRecommenderAgent,
    executor: ManualExecutor,
) -> None:
    @contextmanager
    def factory() -> Iterator[Session]:
        yield db_session

    runner = RecommendationJobRunner(session_factory=factory, executor=executor)
    app.dependency_overrides[get_recommender_agent] = lambda: agent
    app.dependency_overrides[get_market_data_provider] = _provider
    app.dependency_overrides[get_job_runner] = lambda: runner


def test_create_poll_history_and_404(
    client: TestClient, db_session: Session
) -> None:
    agent = FakeRecommenderAgent(
        candidates=[RecommendationCandidate(ticker="ZZTOP", rationale="x")],
        tool_call_count=3,
    )
    executor = ManualExecutor()
    _wire(client, db_session, agent, executor)

    # Create: returns immediately, run still queued.
    created = client.post(
        "/api/v1/recommendations", json={"count": 1, "categories": ["stock"]}
    )
    assert created.status_code == 202
    body = created.json()
    run_id = body["id"]
    assert body["status"] == "queued"
    assert body["requested_categories"] == ["stock"]

    # Drive the deferred job to completion.
    executor.run_pending()

    polled = client.get(f"/api/v1/recommendations/{run_id}")
    assert polled.status_code == 200
    poll_body = polled.json()
    assert poll_body["status"] == "completed"
    assert poll_body["tool_call_count"] == 3
    assert poll_body["prompt"] is not None
    assert {r["ticker"]: r["outcome"] for r in poll_body["results"]}["ZZTOP"] == "added"

    # History includes the run.
    history = client.get("/api/v1/recommendations")
    assert history.status_code == 200
    assert any(item["id"] == run_id for item in history.json())

    # Unknown id -> 404.
    assert client.get("/api/v1/recommendations/99999999").status_code == 404


def test_create_rejects_invalid_count(
    client: TestClient, db_session: Session
) -> None:
    agent = FakeRecommenderAgent(candidates=[], tool_call_count=0)
    _wire(client, db_session, agent, ManualExecutor())

    resp = client.post(
        "/api/v1/recommendations", json={"count": 0, "categories": ["stock"]}
    )
    assert resp.status_code == 422


def test_create_rejects_unsupported_category(
    client: TestClient, db_session: Session
) -> None:
    agent = FakeRecommenderAgent(candidates=[], tool_call_count=0)
    _wire(client, db_session, agent, ManualExecutor())

    resp = client.post(
        "/api/v1/recommendations", json={"count": 1, "categories": ["etf"]}
    )
    assert resp.status_code == 422
