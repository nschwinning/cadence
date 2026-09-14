"""TestClient tests for the read-only paper-trading API.

Seeds a session with trades, runs, and closed positions via the service, then
reads them back through the API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cadence.broker.models import OrderSide
from cadence.paper_trading import service
from cadence.portfolios import service as portfolios_service


def _seed(db_session: Session) -> uuid.UUID:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum"
    )
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=5,
        price=20.0,
        signal_type="entry",
    )
    service.record_session_run(
        db_session, session_id=sess.id, signals_scanned=3, orders_executed=1
    )
    entry = datetime(2026, 1, 1, tzinfo=UTC)
    service.record_closed_position(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        quantity=5,
        entry_price=20.0,
        exit_price=25.0,
        entry_date=entry,
        exit_date=entry + timedelta(days=7),
    )
    return sess.id


def test_list_sessions(client: TestClient, db_session: Session) -> None:
    session_id = _seed(db_session)
    resp = client.get("/api/v1/paper-trading/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["id"] == str(session_id) for item in body["items"])


def test_read_back_trades_runs_positions(
    client: TestClient, db_session: Session
) -> None:
    session_id = _seed(db_session)

    trades = client.get(f"/api/v1/paper-trading/sessions/{session_id}/trades")
    assert trades.status_code == 200
    tbody = trades.json()
    assert tbody["total"] == 1
    assert tbody["items"][0]["ticker"] == "AAPL"
    assert tbody["items"][0]["side"] == "buy"
    assert tbody["items"][0]["notional"] == 100.0

    runs = client.get(f"/api/v1/paper-trading/sessions/{session_id}/runs")
    assert runs.status_code == 200
    rbody = runs.json()
    assert rbody["total"] == 1
    assert rbody["items"][0]["signals_scanned"] == 3

    positions = client.get(
        f"/api/v1/paper-trading/sessions/{session_id}/positions"
    )
    assert positions.status_code == 200
    pbody = positions.json()
    assert pbody["total"] == 1
    assert pbody["items"][0]["realized_pnl"] == 25.0
    assert pbody["items"][0]["holding_days"] == 7


def test_status_filter(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    resp = client.get("/api/v1/paper-trading/sessions", params={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    none_stopped = client.get(
        "/api/v1/paper-trading/sessions", params={"status": "stopped"}
    )
    assert none_stopped.status_code == 200


def test_unknown_session_returns_404(client: TestClient) -> None:
    unknown = uuid.uuid4()
    for suffix in ("trades", "runs", "positions"):
        resp = client.get(
            f"/api/v1/paper-trading/sessions/{unknown}/{suffix}"
        )
        assert resp.status_code == 404
