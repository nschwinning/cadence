"""Tests for the per-portfolio AI cost breakdown (service + HTTP).

The breakdown lists active paper-trading sessions, reads their all-time LiteLLM
spend in a single batched query, and assembles per-portfolio rows plus a grand
total. The batched cost helper is stubbed here so the tests never touch the
LiteLLM database: ``None`` models an unavailable source, a dict models reachable
spend (sessions absent from the dict have no recorded spend and read as ``0``).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cadence.dashboard import service
from cadence.paper_trading import service as paper_trading_service
from cadence.paper_trading.constants import Benchmark, SessionStatus
from cadence.paper_trading.models import PaperTradingSession
from cadence.portfolios import service as portfolios_service


def _make_session(
    db_session: Session,
    *,
    name: str,
    strategy_key: str,
) -> PaperTradingSession:
    portfolio = portfolios_service.create_portfolio(
        db_session, name=name, stocks=["TECH"]
    )
    return paper_trading_service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key=strategy_key,
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )


def _stub_costs(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, float] | None
) -> list[list[str]]:
    """Patch the batched helper to return ``result``; record the ids it was asked for."""
    calls: list[list[str]] = []

    def _fake(session_ids: Sequence[str]) -> dict[str, float] | None:
        calls.append(list(session_ids))
        return result

    monkeypatch.setattr(service, "session_ai_costs_usd", _fake)
    return calls


# --- service ----------------------------------------------------------------


def test_ai_costs_empty_system(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_costs(monkeypatch, {})
    costs = service.get_dashboard_ai_costs(db_session)
    assert costs.portfolios == []
    # Reachable source, no portfolios: the total is the (empty) sum, 0.0.
    assert costs.total_ai_cost_usd == 0.0


def test_ai_costs_rows_sorted_desc_with_total(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    low = _make_session(db_session, name="Low", strategy_key="s1")
    high = _make_session(db_session, name="High", strategy_key="s2")
    _stub_costs(monkeypatch, {str(low.id): 2.0, str(high.id): 7.5})

    costs = service.get_dashboard_ai_costs(db_session)

    assert [p.session_id for p in costs.portfolios] == [str(high.id), str(low.id)]
    assert [p.ai_cost_usd for p in costs.portfolios] == [7.5, 2.0]
    assert costs.total_ai_cost_usd == 9.5


def test_ai_costs_zero_spend_distinct_from_unavailable(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    spent = _make_session(db_session, name="Spent", strategy_key="s1")
    quiet = _make_session(db_session, name="Quiet", strategy_key="s2")
    # Only ``spent`` is in the map; ``quiet`` has no recorded spend => 0.
    _stub_costs(monkeypatch, {str(spent.id): 3.0})

    costs = service.get_dashboard_ai_costs(db_session)

    by_id = {p.session_id: p.ai_cost_usd for p in costs.portfolios}
    assert by_id[str(spent.id)] == 3.0
    assert by_id[str(quiet.id)] == 0.0
    assert costs.total_ai_cost_usd == 3.0


def test_ai_costs_unavailable_degrades_to_null(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_session(db_session, name="Alpha", strategy_key="s1")
    _stub_costs(monkeypatch, None)

    costs = service.get_dashboard_ai_costs(db_session)

    assert len(costs.portfolios) == 1
    assert costs.portfolios[0].ai_cost_usd is None
    assert costs.total_ai_cost_usd is None


def test_ai_costs_excludes_stopped_and_archived(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = _make_session(db_session, name="Active", strategy_key="s1")
    stopped = _make_session(db_session, name="Stopped", strategy_key="s2")
    archived = _make_session(db_session, name="Archived", strategy_key="s3")
    paper_trading_service.update_session_status(
        db_session, stopped.id, SessionStatus.STOPPED
    )
    paper_trading_service.update_session_status(
        db_session, archived.id, SessionStatus.STOPPED
    )
    paper_trading_service.archive_session(db_session, archived.id)

    calls = _stub_costs(monkeypatch, {str(active.id): 1.0})
    costs = service.get_dashboard_ai_costs(db_session)

    assert [p.session_id for p in costs.portfolios] == [str(active.id)]
    # Only the active session's id is ever passed to the cost query.
    assert calls == [[str(active.id)]]


def test_ai_costs_label_is_portfolio_name(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _make_session(db_session, name="Blue Whale", strategy_key="strat-a")
    _stub_costs(monkeypatch, {str(row.id): 1.0})

    costs = service.get_dashboard_ai_costs(db_session)
    # Label is the traded portfolio's display name, as the dashboard pages show it.
    assert costs.portfolios[0].label == "Blue Whale"


# --- HTTP layer -------------------------------------------------------------


def test_ai_costs_endpoint_returns_payload(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _make_session(db_session, name="Alpha", strategy_key="s1")
    _stub_costs(monkeypatch, {str(row.id): 4.25})

    response = client.get("/api/v1/dashboard/ai-costs")

    assert response.status_code == 200
    body = response.json()
    assert body["total_ai_cost_usd"] == 4.25
    assert body["portfolios"] == [
        {"session_id": str(row.id), "label": "Alpha", "ai_cost_usd": 4.25}
    ]


def test_ai_costs_endpoint_degrades_to_null(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_session(db_session, name="Alpha", strategy_key="s1")
    _stub_costs(monkeypatch, None)

    response = client.get("/api/v1/dashboard/ai-costs")

    assert response.status_code == 200
    body = response.json()
    assert body["total_ai_cost_usd"] is None
    assert body["portfolios"][0]["ai_cost_usd"] is None
