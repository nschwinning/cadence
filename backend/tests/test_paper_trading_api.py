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
from cadence.assets.category import AssetCategory
from cadence.assets.models import Asset
from cadence.assets.sector import Sector
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
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
    # The frozen crypto-rebalance-prompt version is exposed alongside it.
    assert item["crypto_rebalance_prompt_version"] == 1
    # The traded portfolio's name is surfaced so the client can label the session.
    assert item["portfolio_name"] == "P"


def test_list_sessions_exposes_stop_loss_config(
    client: TestClient, db_session: Session
) -> None:
    # The stop-loss opt-in and threshold are surfaced read-only on the session read.
    portfolio = portfolios_service.create_portfolio(
        db_session, name="SL", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
        stop_loss_enabled=True,
        stop_loss_pct=0.2,
    )

    resp = client.get("/api/v1/paper-trading/sessions")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["id"] == str(sess.id))
    assert item["stop_loss_enabled"] is True
    assert item["stop_loss_pct"] == 0.2


def test_list_sessions_defaults_stop_loss_disabled(
    client: TestClient, db_session: Session
) -> None:
    session_id = _seed(db_session)  # created without a stop-loss
    resp = client.get("/api/v1/paper-trading/sessions")
    item = next(i for i in resp.json()["items"] if i["id"] == str(session_id))
    assert item["stop_loss_enabled"] is False
    assert item["stop_loss_pct"] is None


def test_list_sessions_exposes_guardrail_config(
    client: TestClient, db_session: Session
) -> None:
    # The frozen risk-guardrail opt-in and parameters are surfaced read-only.
    portfolio = portfolios_service.create_portfolio(
        db_session, name="GR", stocks=["AAPL"], max_allocation_pct=0.25
    )
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
        max_allocation_pct=0.25,
        risk_guardrails_enabled=True,
        max_asset_class_pct=0.6,
        min_positions=5,
        max_invested_pct=0.9,
    )

    resp = client.get("/api/v1/paper-trading/sessions")
    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["id"] == str(sess.id))
    assert item["risk_guardrails_enabled"] is True
    assert item["max_allocation_pct"] == 0.25
    assert item["max_asset_class_pct"] == 0.6
    assert item["min_positions"] == 5
    assert item["max_invested_pct"] == 0.9


def test_list_sessions_defaults_guardrails_disabled(
    client: TestClient, db_session: Session
) -> None:
    # A session created before/without guardrails reports them off with null params
    # and the no-op 1.0 per-asset cap.
    session_id = _seed(db_session)
    resp = client.get("/api/v1/paper-trading/sessions")
    item = next(i for i in resp.json()["items"] if i["id"] == str(session_id))
    assert item["risk_guardrails_enabled"] is False
    assert item["max_allocation_pct"] == 1.0
    assert item["max_asset_class_pct"] is None
    assert item["min_positions"] is None
    assert item["max_invested_pct"] is None


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
    # A non-AI run (recorded without an event) exposes a null AI-event reference.
    assert rbody["items"][0]["ai_portfolio_event_id"] is None

    positions = client.get(
        f"/api/v1/paper-trading/sessions/{session_id}/positions"
    )
    assert positions.status_code == 200
    pbody = positions.json()
    assert pbody["total"] == 1
    assert pbody["items"][0]["realized_pnl"] == 25.0
    assert pbody["items"][0]["holding_days"] == 7


def test_trades_runs_positions_paginate_by_limit_and_offset(
    client: TestClient, db_session: Session
) -> None:
    # Seed a session with several trades, runs, and closed positions, then page.
    session_id = _seed(db_session)  # already has 1 of each
    for i in range(4):  # -> 5 of each in total
        service.record_trade(
            db_session,
            session_id=session_id,
            ticker="MSFT",
            side=OrderSide.BUY,
            quantity=1,
            price=float(i + 1),
            signal_type="entry",
        )
        service.record_session_run(
            db_session, session_id=session_id, signals_scanned=i, orders_executed=1
        )
        entry = datetime(2026, 2, i + 1, tzinfo=UTC)
        service.record_closed_position(
            db_session,
            session_id=session_id,
            ticker="MSFT",
            quantity=1,
            entry_price=1.0,
            exit_price=2.0,
            entry_date=entry,
            exit_date=entry + timedelta(days=1),
        )

    base = f"/api/v1/paper-trading/sessions/{session_id}"
    for path in ("trades", "runs", "positions"):
        first = client.get(f"{base}/{path}", params={"limit": 2, "offset": 0})
        assert first.status_code == 200
        fbody = first.json()
        assert fbody["total"] == 5
        assert len(fbody["items"]) == 2

        second = client.get(f"{base}/{path}", params={"limit": 2, "offset": 2})
        assert second.json()["total"] == 5
        assert len(second.json()["items"]) == 2
        # The window advanced: the two pages do not overlap.
        first_ids = {i["id"] for i in fbody["items"]}
        second_ids = {i["id"] for i in second.json()["items"]}
        assert first_ids.isdisjoint(second_ids)

        # Offset past the end -> empty page, true total preserved.
        beyond = client.get(f"{base}/{path}", params={"limit": 2, "offset": 99})
        assert beyond.json()["total"] == 5
        assert beyond.json()["items"] == []

        # A negative offset is rejected.
        assert (
            client.get(f"{base}/{path}", params={"limit": 2, "offset": -1}).status_code
            == 422
        )


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
        db_session, portfolio_id=portfolio.id, strategy_key=strategy_key, rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
        db_session, portfolio_id=portfolio.id, strategy_key="active", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
        db_session, portfolio_id=portfolio.id, strategy_key="recon", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
        db_session, portfolio_id=portfolio.id, strategy_key="ai_buy_hold", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
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


def test_value_history_comparison_lists_non_archived_sessions(
    client: TestClient, db_session: Session
) -> None:
    broker = StubBroker()

    # Session A: two snapshots, resolvable portfolio name.
    port_a = portfolios_service.create_portfolio(
        db_session, name="Alpha", stocks=["AAPL"]
    )
    sess_a = service.create_session(
        db_session,
        portfolio_id=port_a.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    for day in (date(2026, 1, 6), date(2026, 1, 4)):
        service.record_value_snapshot(
            db_session, session_id=sess_a.id, as_of=day, broker=broker
        )

    # Session B: no snapshots yet -> included with empty points.
    port_b = portfolios_service.create_portfolio(
        db_session, name="Beta", stocks=["MSFT"]
    )
    sess_b = service.create_session(
        db_session,
        portfolio_id=port_b.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )

    # Session C: archived -> excluded.
    port_c = portfolios_service.create_portfolio(
        db_session, name="Gamma", stocks=["AAPL"]
    )
    sess_c = service.create_session(
        db_session,
        portfolio_id=port_c.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    service.record_value_snapshot(
        db_session, session_id=sess_c.id, as_of=date(2026, 1, 5), broker=broker
    )
    service.update_session_status(db_session, sess_c.id, SessionStatus.STOPPED)
    service.archive_session(db_session, sess_c.id)

    resp = client.get("/api/v1/paper-trading/sessions/value-history-comparison")
    assert resp.status_code == 200
    body = resp.json()
    by_id = {s["session_id"]: s for s in body["sessions"]}

    assert str(sess_c.id) not in by_id
    assert set(by_id) == {str(sess_a.id), str(sess_b.id)}

    a = by_id[str(sess_a.id)]
    assert a["label"] == "Alpha"
    assert a["allocated_capital"] == pytest.approx(100_000.0)
    assert [p["snapshot_date"] for p in a["points"]] == ["2026-01-04", "2026-01-06"]

    b = by_id[str(sess_b.id)]
    assert b["label"] == "Beta"
    assert b["points"] == []


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
        db_session, portfolio_id=portfolio.id, strategy_key="ai_kpis", rebalance_prompt_version=1, crypto_rebalance_prompt_version=1, benchmark=Benchmark.SP500)
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
        "unallocated_cash",
        "realised_pnl",
        "unrealised_pnl",
        "total_fees",
        "daily_avg_transaction_cost",
        "total_return",
        "total_return_pct",
        "sharpe_ratio",
        "benchmark",
        "benchmark_return_pct",
        "excess_return_pct",
        "excess_return",
        "max_drawdown",
        "win_rate",
        "average_win",
        "average_loss",
        "best_trade",
        "worst_trade",
    }
    # Ledger buy above did not go through record_trade, so no fees accrued.
    assert body["total_fees"] == 0.0
    # No daily snapshots yet -> daily average transaction cost withheld.
    assert body["daily_avg_transaction_cost"] is None
    assert body["current_value"] == 100_200.0
    # Unallocated cash = live value minus the 10 AAPL @ $120 ($1,200) position.
    assert body["unallocated_cash"] == 99_000.0
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
    assert body["excess_return"] is None
    # No value snapshots and no closed positions -> the new metrics are withheld.
    assert body["max_drawdown"] is None
    assert body["win_rate"] is None
    assert body["average_win"] is None
    assert body["average_loss"] is None
    assert body["best_trade"] is None
    assert body["worst_trade"] is None


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
        rebalance_prompt_version=1, crypto_rebalance_prompt_version=1,
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
    # Absolute excess equals the fractional excess on allocated capital.
    allocated = body["current_value"] - body["total_return"]
    assert body["excess_return"] == pytest.approx(
        body["excess_return_pct"] * allocated
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


def test_session_sector_performance_returns_groupings(
    client: TestClient, db_session: Session
) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="AI", stocks=["AAPL"]
    )
    sess = service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_sectors",
        rebalance_prompt_version=1,
        crypto_rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
    )
    db_session.add_all(
        [
            Asset(
                ticker="AAPL",
                category=AssetCategory.STOCK.value,
                sector=Sector.TECHNOLOGY.value,
                currency="USD",
                is_eligible=True,
                criteria_results=[],
            ),
            Asset(
                ticker="BTC-USD",
                category=AssetCategory.CRYPTO.value,
                sector=None,
                currency="USD",
                is_eligible=True,
                criteria_results=[],
            ),
        ]
    )
    db_session.commit()
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="AAPL",
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker="BTC-USD",
        side=OrderSide.BUY,
        shares=1,
        price=1000.0,
    )
    app.dependency_overrides[get_broker] = lambda: _QuoteBroker(
        {"AAPL": 120.0, "BTC-USD": 1200.0}
    )

    resp = client.get(
        f"/api/v1/paper-trading/sessions/{sess.id}/sector-performance"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"by_sector", "by_category"}
    sector_keys = {g["key"] for g in body["by_sector"]}
    # The equity lands in tech; the crypto (no sector) in the "No sector" bucket.
    assert sector_keys == {Sector.TECHNOLOGY.value, "No sector"}
    category_keys = {g["key"] for g in body["by_category"]}
    assert category_keys == {AssetCategory.STOCK.value, AssetCategory.CRYPTO.value}
    tech = next(g for g in body["by_sector"] if g["key"] == Sector.TECHNOLOGY.value)
    assert tech["total_pnl"] == pytest.approx(200.0)
    assert tech["return_pct"] == pytest.approx(0.2)


def test_session_sector_performance_unknown_session_404(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_broker] = lambda: _QuoteBroker({})
    resp = client.get(
        f"/api/v1/paper-trading/sessions/{uuid.uuid4()}/sector-performance"
    )
    assert resp.status_code == 404
