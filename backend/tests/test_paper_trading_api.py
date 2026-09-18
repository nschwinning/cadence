"""TestClient tests for the read-only paper-trading API.

Seeds a session with trades, runs, and closed positions via the service, then
reads them back through the API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cadence.api.app import app
from cadence.broker import get_broker
from cadence.broker.models import AssetClass, Order, OrderSide, OrderStatus, Quote
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service
from cadence.paper_trading.constants import (
    BENCHMARK_DISPLAY_NAMES,
    Benchmark,
    SessionStatus,
)
from cadence.paper_trading.models import BenchmarkPrice
from cadence.portfolios import service as portfolios_service


class _OrderBroker:
    """Broker double returning pre-seeded orders keyed by order id."""

    def __init__(self, orders: dict[str, Order | None]) -> None:
        self._orders = orders

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)


def _seed(db_session: Session) -> uuid.UUID:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
    item = next(item for item in body["items"] if item["id"] == str(session_id))
    # The frozen rebalance-prompt version is exposed on the read model.
    assert item["rebalance_prompt_version"] == 1
    # The traded portfolio's name is surfaced so the client can label the session.
    assert item["portfolio_name"] == "P"


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
    for suffix in ("trades", "runs", "positions", "value-history", "kpis"):
        resp = client.get(
            f"/api/v1/paper-trading/sessions/{unknown}/{suffix}"
        )
        assert resp.status_code == 404


def _stopped_session_id(db_session: Session, strategy_key: str = "arch") -> uuid.UUID:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key=strategy_key, rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    service.update_session_status(db_session, sess.id, SessionStatus.STOPPED)
    return sess.id


def test_archive_and_unarchive_session(
    client: TestClient, db_session: Session
) -> None:
    session_id = _stopped_session_id(db_session)

    archived = client.post(
        f"/api/v1/paper-trading/sessions/{session_id}/archive"
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    # Archived sessions drop out of the default list, return with the flag.
    default = client.get("/api/v1/paper-trading/sessions")
    assert all(item["id"] != str(session_id) for item in default.json()["items"])
    with_archived = client.get(
        "/api/v1/paper-trading/sessions", params={"include_archived": "true"}
    )
    assert any(
        item["id"] == str(session_id) for item in with_archived.json()["items"]
    )

    restored = client.post(
        f"/api/v1/paper-trading/sessions/{session_id}/unarchive"
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


def test_archive_non_stopped_session_conflicts(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="active", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    resp = client.post(f"/api/v1/paper-trading/sessions/{sess.id}/archive")
    assert resp.status_code == 409


def test_archive_unknown_session_404(client: TestClient) -> None:
    unknown = uuid.uuid4()
    assert (
        client.post(f"/api/v1/paper-trading/sessions/{unknown}/archive").status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/paper-trading/sessions/{unknown}/unarchive"
        ).status_code
        == 404
    )


def test_reconcile_session_returns_counts_and_refreshed_trades(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="P", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="recon", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    service.record_trade(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        quantity=5,
        price=20.0,
        signal_type="entry",
        order_id="o1",
        order_status=OrderStatus.SUBMITTED,
    )
    filled = Order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5,
        asset_class=AssetClass.EQUITY,
        order_id="o1",
        status=OrderStatus.FILLED,
        filled_quantity=5,
        filled_price=20.0,
    )
    app.dependency_overrides[get_broker] = lambda: _OrderBroker({"o1": filled})

    resp = client.post(f"/api/v1/paper-trading/sessions/{sess.id}/reconcile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trades_seen"] == 1
    assert body["trades_reconciled"] == 1
    assert body["trades_filled"] == 1
    # The refreshed trades reflect the reconciled status.
    assert body["trades"][0]["order_status"] == "filled"


def test_reconcile_unknown_session_404(client: TestClient) -> None:
    unknown = uuid.uuid4()
    resp = client.post(f"/api/v1/paper-trading/sessions/{unknown}/reconcile")
    assert resp.status_code == 404


def test_value_history_ascending(client: TestClient, db_session: Session) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="ai_buy_hold", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    broker = StubBroker()
    # Record out of order; the endpoint must return them oldest date first.
    for day in (date(2026, 1, 6), date(2026, 1, 4), date(2026, 1, 5)):
        service.record_value_snapshot(
            db_session, session_id=sess.id, as_of=day, broker=broker
        )

    resp = client.get(f"/api/v1/paper-trading/sessions/{sess.id}/value-history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    dates = [item["snapshot_date"] for item in body["items"]]
    assert dates == ["2026-01-04", "2026-01-05", "2026-01-06"]
    # The snapshot fields are exposed on each item, including the benchmark value
    # (null here since no benchmark prices are stored).
    first = body["items"][0]
    assert {"total_value", "cash_value", "positions_value", "daily_pnl"} <= first.keys()
    assert all("benchmark_value" in item for item in body["items"])
    assert first["benchmark_value"] is None


def test_value_history_carries_rebased_benchmark_value(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_vh_bench",
        rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    broker = StubBroker()
    start = date(2026, 1, 5)
    later = date(2026, 1, 6)
    for day in (start, later):
        service.record_value_snapshot(
            db_session, session_id=sess.id, as_of=day, broker=broker
        )
    # Benchmark up 20% between the two snapshot dates.
    db_session.add(BenchmarkPrice(benchmark="SP500", price_date=start, close=100.0))
    db_session.add(BenchmarkPrice(benchmark="SP500", price_date=later, close=120.0))
    db_session.commit()

    resp = client.get(f"/api/v1/paper-trading/sessions/{sess.id}/value-history")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Rebased to allocated capital on the first snapshot date, then +20%.
    assert items[0]["benchmark_value"] == 100_000.0
    assert items[1]["benchmark_value"] == 120_000.0


class _QuoteBroker:
    """Broker double pricing configured tickers, for the live KPI endpoint."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = prices

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {
            sym: Quote(symbol=sym, bid=p, ask=p, last=p)
            for sym, p in self._prices.items()
            if sym in symbols
        }


def test_session_kpis_returns_live_figures(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="ai_kpis", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    app.dependency_overrides[get_broker] = lambda: _QuoteBroker({"AAPL": 120.0})

    resp = client.get(f"/api/v1/paper-trading/sessions/{sess.id}/kpis")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "current_value",
        "realised_pnl",
        "unrealised_pnl",
        "total_fees",
        "total_return",
        "total_return_pct",
        "sharpe_ratio",
        "benchmark",
        "benchmark_return_pct",
        "excess_return_pct",
    }
    # Ledger buy above did not go through record_trade, so no fees accrued.
    assert body["total_fees"] == 0.0
    assert body["current_value"] == 100_200.0
    assert body["realised_pnl"] == 0.0
    assert body["unrealised_pnl"] == 200.0
    assert body["total_return"] == 200.0
    assert body["total_return_pct"] == 200.0 / 100_000.0
    # No daily snapshots yet -> Sharpe withheld.
    assert body["sharpe_ratio"] is None
    # The session's benchmark id is echoed; with no stored benchmark prices the
    # comparison figures degrade to null.
    assert body["benchmark"] == Benchmark.SP500.value
    assert body["benchmark_return_pct"] is None
    assert body["excess_return_pct"] is None


def test_session_kpis_benchmark_comparison_from_stored_prices(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_kpis_bench",
        rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    # One snapshot anchors the session's start date for the benchmark rebase.
    broker = StubBroker()
    start = date(2026, 1, 5)
    service.record_value_snapshot(
        db_session, session_id=sess.id, as_of=start, broker=broker
    )
    # Benchmark rose 10% from the session's start close to the latest close.
    db_session.add(BenchmarkPrice(benchmark="SP500", price_date=start, close=100.0))
    db_session.add(
        BenchmarkPrice(
            benchmark="SP500", price_date=start + timedelta(days=30), close=110.0
        )
    )
    db_session.commit()
    app.dependency_overrides[get_broker] = lambda: _QuoteBroker({"AAPL": 120.0})

    resp = client.get(f"/api/v1/paper-trading/sessions/{sess.id}/kpis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["benchmark"] == "SP500"
    assert body["benchmark_return_pct"] == pytest.approx(0.10)
    # Excess return is the session's total return minus the benchmark's.
    assert body["excess_return_pct"] == pytest.approx(
        body["total_return_pct"] - body["benchmark_return_pct"]
    )


# --------------------------------------------------------------------------- #
# Benchmark catalog + change-benchmark endpoints
# --------------------------------------------------------------------------- #


def test_list_benchmarks_returns_full_catalog(client: TestClient) -> None:
    resp = client.get("/api/v1/paper-trading/benchmarks")
    assert resp.status_code == 200
    body = resp.json()
    # All eight catalog benchmarks are listed as {id, name}.
    assert len(body) == len(Benchmark)
    by_id = {entry["id"]: entry["name"] for entry in body}
    assert set(by_id) == {b.value for b in Benchmark}
    for member, name in BENCHMARK_DISPLAY_NAMES.items():
        assert by_id[member.value] == name


def test_change_benchmark_persists_new_selection(
    client: TestClient, db_session: Session
) -> None:
    session_id = _seed(db_session)
    resp = client.put(
        f"/api/v1/paper-trading/sessions/{session_id}/benchmark",
        json={"benchmark": "DJIA"},
    )
    assert resp.status_code == 200
    assert resp.json()["benchmark"] == "DJIA"
    # The change persisted on the row.
    assert service.get_session(db_session, session_id).benchmark == "DJIA"


def test_change_benchmark_unknown_session_is_404(client: TestClient) -> None:
    resp = client.put(
        f"/api/v1/paper-trading/sessions/{uuid.uuid4()}/benchmark",
        json={"benchmark": "DJIA"},
    )
    assert resp.status_code == 404


def test_change_benchmark_invalid_id_is_422(
    client: TestClient, db_session: Session
) -> None:
    session_id = _seed(db_session)
    resp = client.put(
        f"/api/v1/paper-trading/sessions/{session_id}/benchmark",
        json={"benchmark": "NOT_A_REAL_INDEX"},
    )
    assert resp.status_code == 422
    # The session's benchmark is left unchanged.
    assert service.get_session(db_session, session_id).benchmark == "SP500"
