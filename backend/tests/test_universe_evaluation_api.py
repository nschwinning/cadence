"""TestClient tests for the universe-evaluation API (fake agent, no network)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeUniverseEvaluationAgent

from cadence.api.app import app
from cadence.api.routers.assets import get_universe_evaluation_agent
from cadence.assets.category import AssetCategory
from cadence.assets.errors import AssetEvaluationUnavailableError
from cadence.assets.models import Asset

_GET = "/api/v1/assets/universe-evaluation"
_REFRESH = "/api/v1/assets/universe-evaluation/refresh"


def _asset(ticker: str, *, sector: str | None = "technology") -> Asset:
    return Asset(
        ticker=ticker,
        name=f"{ticker} Co",
        alpaca_symbol=ticker,
        fractionable=True,
        category=AssetCategory.STOCK.value,
        sector=sector,
        exchange="XETRA",
        currency="USD",
        country="United States",
        is_eligible=True,
        market_cap_usd=5_000_000_000.0,
        avg_daily_turnover_usd=10_000_000.0,
        history_years=10.0,
        criteria_results=[],
    )


def _seed(db_session: Session, *tickers: str) -> None:
    for ticker in tickers:
        db_session.add(_asset(ticker))
    db_session.commit()


def _use_agent(agent: FakeUniverseEvaluationAgent) -> None:
    app.dependency_overrides[get_universe_evaluation_agent] = lambda: agent


@pytest.fixture(autouse=True)
def _clear_agent_override() -> Iterator[None]:
    yield
    app.dependency_overrides.pop(get_universe_evaluation_agent, None)


def test_get_lazy_generates_when_none_exists(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, "AAA", "BBB")
    agent = FakeUniverseEvaluationAgent()
    _use_agent(agent)

    response = client.get(_GET)

    assert response.status_code == 200
    body = response.json()["evaluation"]
    assert body is not None
    assert body["narrative"] == "A reasonably diversified universe."
    assert body["strengths"] == ["Broad sector coverage"]
    assert body["outdated"] is False
    assert len(agent.evaluate_calls) == 1


def test_second_get_does_not_regenerate(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, "AAA")
    agent = FakeUniverseEvaluationAgent()
    _use_agent(agent)

    client.get(_GET)
    client.get(_GET)

    assert len(agent.evaluate_calls) == 1


def test_get_flags_outdated_after_asset_mutation(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, "AAA")
    _use_agent(FakeUniverseEvaluationAgent())

    first = client.get(_GET).json()["evaluation"]
    assert first["outdated"] is False

    _seed(db_session, "BBB")  # universe changed

    second = client.get(_GET).json()["evaluation"]
    assert second["outdated"] is True


def test_refresh_regenerates(client: TestClient, db_session: Session) -> None:
    _seed(db_session, "AAA")
    agent = FakeUniverseEvaluationAgent()
    _use_agent(agent)

    client.get(_GET)  # initial fill (1 call)
    _seed(db_session, "BBB")  # make it outdated

    response = client.post(_REFRESH)

    assert response.status_code == 200
    body = response.json()["evaluation"]
    assert body["outdated"] is False
    assert len(agent.evaluate_calls) == 2


def test_empty_universe_returns_null_without_calling_agent(
    client: TestClient,
) -> None:
    agent = FakeUniverseEvaluationAgent()
    _use_agent(agent)

    response = client.get(_GET)

    assert response.status_code == 200
    assert response.json()["evaluation"] is None
    assert agent.evaluate_calls == []


def test_agent_failure_returns_502(
    client: TestClient, db_session: Session
) -> None:
    _seed(db_session, "AAA")
    _use_agent(
        FakeUniverseEvaluationAgent(
            error=AssetEvaluationUnavailableError("provider down")
        )
    )

    response = client.get(_GET)

    assert response.status_code == 502
