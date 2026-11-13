"""Router tests for the strategy-bot API (lifecycle, reads, cron jobs)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.fakes import FakeBotSummaryAgent, RecordingNotifier

from cadence.api.app import app
from cadence.api.routers.bots import get_bot_summary_agent
from cadence.assets.models import Asset
from cadence.broker.models import OrderSide
from cadence.config import settings
from cadence.notify import get_notifier
from cadence.strategy_bots.market_data import StubMarketData, get_market_data
from cadence.strategy_bots.models import BotTrade, BotValuePoint, BotValueSnapshot


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
def fake_summary_agent() -> Iterator[FakeBotSummaryAgent]:
    """Override the summary-agent DI so no network call is made on summary reads."""
    agent = FakeBotSummaryAgent()
    app.dependency_overrides[get_bot_summary_agent] = lambda: agent
    try:
        yield agent
    finally:
        app.dependency_overrides.pop(get_bot_summary_agent, None)


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


def test_create_donchian_turtle_session(
    client: TestClient, eligible_asset: Asset
) -> None:
    """A Donchian Turtle session is created end-to-end through the service."""
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_create_payload(
            strategy_key="donchian_breakout",
            strategy_params={
                "version": "turtle",
                "entry_period": 20,
                "exit_period": 10,
            },
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["strategy_key"] == "donchian_breakout"


def test_create_donchian_locked_session(
    client: TestClient, eligible_asset: Asset
) -> None:
    """A Donchian Locked session is created end-to-end through the service."""
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_create_payload(
            strategy_key="donchian_breakout",
            strategy_params={
                "version": "locked",
                "channel_period": 20,
                "atr_padding_mult": 0.5,
            },
        ),
    )
    assert resp.status_code == 201
    assert resp.json()["strategy_key"] == "donchian_breakout"


def test_create_rejects_invalid_donchian_params(
    client: TestClient, eligible_asset: Asset
) -> None:
    """exit_period not below entry_period is rejected on create."""
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_create_payload(
            strategy_key="donchian_breakout",
            strategy_params={"entry_period": 10, "exit_period": 10},
        ),
    )
    assert resp.status_code == 422


def test_list_presets(client: TestClient) -> None:
    resp = client.get("/api/v1/bots/presets")
    assert resp.status_code == 200
    body = resp.json()
    assert [p["key"] for p in body] == [
        "ma_crossover_algo6",
        "rsi_mean_reversion_algo16",
        "donchian_turtle_algo25",
        "donchian_smart_range_algo8",
        "rolling_reversion_sma_band_algo5",
        "rolling_reversion_zscore_algo4",
        "rolling_reversion_mean_cross_algo14",
        "rolling_reversion_vwap_cross_algo39",
        "atr_band_supertrend_algo9",
        "atr_band_keltner_algo21",
        "adx_trend_algo12",
        "rolling_reversion_vwap_adx_algo15",
        "macd_momentum_algo10",
        "heikin_ashi_algo11",
        "heikin_ashi_volume_algo37",
        "hma_trend_algo19",
        "ma_ribbon_algo18",
        "vama_algo30",
        "rolling_reversion_gradient_algo3",
        "price_velocity_algo48",
        "trend_confirmation_cadence",
        "volume_spike_algo34",
        "volume_spike_simple_algo34",
        "vroc_breakout_algo46",
        "chaikin_oscillator_algo45",
    ]
    turtle = body[2]
    assert turtle == {
        "key": "donchian_turtle_algo25",
        "display_name": "Turtle Breakout (Algo 25)",
        "description": turtle["description"],
        "course_ref": "Algo 25",
        "strategy_key": "donchian_breakout",
        "strategy_params": {"version": "turtle", "entry_period": 20, "exit_period": 10},
        "take_profit_pct": None,
        "stop_loss_pct": None,
        "drawdown_stop_pct": 0.05,
        "is_default": True,
    }
    assert turtle["description"]
    assert body[3]["is_default"] is False


def _preset_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "preset_key": "ma_crossover_algo6",
        "tickers": ["AAPL"],
        "initial_capital": 100_000.0,
        "benchmark": "SP500",
    }
    payload.update(overrides)
    return payload


def test_create_from_preset_without_overrides(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post("/api/v1/bots/sessions", json=_preset_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["strategy_key"] == "ma_crossover"
    assert body["strategy_params"] == {"fast_period": 5, "slow_period": 12}
    assert body["take_profit_pct"] == 0.01
    assert body["stop_loss_pct"] == 0.02
    assert body["drawdown_stop_pct"] == 0.05
    assert body["preset_key"] == "ma_crossover_algo6"
    assert body["preset_customized"] is False
    assert body["origin"] == "manual"


def test_create_from_preset_with_override_is_customized(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions", json=_preset_payload(stop_loss_pct=None)
    )
    assert resp.status_code == 201
    body = resp.json()
    # Explicit null turns the preset's stop-loss off; omitted TP is inherited.
    assert body["stop_loss_pct"] is None
    assert body["take_profit_pct"] == 0.01
    assert body["preset_customized"] is True


def test_create_from_unknown_preset_422(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions", json=_preset_payload(preset_key="nope")
    )
    assert resp.status_code == 422


def test_create_from_preset_mismatched_strategy_422(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post(
        "/api/v1/bots/sessions",
        json=_preset_payload(strategy_key="rsi_mean_reversion"),
    )
    assert resp.status_code == 422


def test_create_without_preset_reports_no_provenance(
    client: TestClient, eligible_asset: Asset
) -> None:
    resp = client.post("/api/v1/bots/sessions", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["preset_key"] is None
    assert body["preset_customized"] is False
    assert body["origin"] == "manual"
    assert body["orchestrator_id"] is None
    assert body["orchestrator_label"] is None


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
    # Each listed session carries its live value (cost-basis before any snapshot) and
    # a separate end-of-day value that is null until a daily snapshot exists.
    assert listed.json()["items"][0]["current_value"] == 100_000.0
    assert listed.json()["items"][0]["eod_value"] is None

    detail = client.get(f"/api/v1/bots/sessions/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert detail.json()["current_value"] == 100_000.0
    assert detail.json()["eod_value"] is None


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
    # Available cash is surfaced on the KPIs (all cash before any position opens).
    assert kpis.json()["cash"] == 100_000.0
    # Sharpe is serialized; null until the session has enough snapshot history.
    assert kpis.json()["sharpe_ratio"] is None
    # No closed round-trip yet → best/worst trade null.
    assert kpis.json()["best_trade"] is None
    assert kpis.json()["worst_trade"] is None
    # Benchmark id is serialized; its return/excess are null until a snapshot exists.
    assert kpis.json()["benchmark"] == "SP500"
    assert kpis.json()["benchmark_return_pct"] is None
    assert kpis.json()["excess_return_pct"] is None
    # Live-value freshness + separate end-of-day value: all absent before any snapshot.
    assert kpis.json()["eod_value"] is None
    assert kpis.json()["value_as_of"] is None
    assert kpis.json()["value_is_intraday"] is False

    history = client.get(f"/api/v1/bots/sessions/{sid}/value-history")
    assert history.status_code == 200
    assert history.json()["total"] == 0

    trades = client.get(f"/api/v1/bots/sessions/{sid}/trades")
    assert trades.status_code == 200
    assert trades.json()["total"] == 0


def test_kpis_report_best_and_worst_closed_trade(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    # One closed round-trip: buy 10 @ 50, sell 10 @ 56 → +60 realized.
    db_session.add_all(
        [
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.BUY.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=50.0,
                fees=0.0,
                created_at=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
            ),
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.SELL.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=56.0,
                fees=0.0,
                created_at=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.flush()

    body = client.get(f"/api/v1/bots/sessions/{sid}/kpis").json()
    best = body["best_trade"]
    assert best["ticker"] == "AAPL"
    assert best["realised_pnl"] == 60.0
    # The round-trip now carries its exact entry/exit fills.
    assert best["quantity"] == 10.0
    assert best["entry_price"] == 50.0
    assert best["entry_at"].startswith("2026-01-06")
    assert best["exit_price"] == 56.0
    assert best["exit_at"].startswith("2026-01-07")
    assert body["worst_trade"]["ticker"] == "AAPL"
    assert body["worst_trade"]["realised_pnl"] == 60.0


def test_trades_pagination(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    for minute in range(3):
        db_session.add(
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.BUY.value,
                ticker="AAPL",
                quantity=1.0,
                filled_price=10.0,
                fees=0.0,
                created_at=datetime(2026, 1, 6, 9, minute, tzinfo=UTC),
            )
        )
    db_session.flush()

    # Default page: full total, bounded items, most-recent-first.
    first = client.get(f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 2})
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    # Second page via offset.
    second = client.get(
        f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 2, "offset": 2}
    )
    assert second.json()["total"] == 3
    assert len(second.json()["items"]) == 1


def test_trades_pagination_rejects_bad_params(
    client: TestClient, eligible_asset: Asset
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"limit": 101}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/bots/sessions/{sid}/trades", params={"offset": -1}
        ).status_code
        == 422
    )


def test_trades_unknown_session_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000/trades"
    )
    assert resp.status_code == 404


# Session summary ---------------------------------------------------------
def test_summary_stopped_session_returns_stats_and_narrative(
    client: TestClient,
    eligible_asset: Asset,
    db_session: Session,
    fake_summary_agent: FakeBotSummaryAgent,
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    # One closed round-trip so the stats carry a best/worst trade.
    db_session.add_all(
        [
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.BUY.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=50.0,
                fees=0.0,
                created_at=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
            ),
            BotTrade(
                bot_session_id=uuid.UUID(sid),
                side=OrderSide.SELL.value,
                ticker="AAPL",
                quantity=10.0,
                filled_price=55.0,
                fees=0.0,
                created_at=datetime(2026, 1, 7, 9, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.flush()
    client.post(f"/api/v1/bots/sessions/{sid}/stop")

    resp = client.get(f"/api/v1/bots/sessions/{sid}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["stop_reason"] == "manual"
    assert body["stats"]["trade_count"] == 1
    assert body["stats"]["best_trade"]["ticker"] == "AAPL"
    assert body["narrative"] is not None
    assert fake_summary_agent.calls == 1


def test_summary_active_session_conflicts(
    client: TestClient,
    eligible_asset: Asset,
    fake_summary_agent: FakeBotSummaryAgent,
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    resp = client.get(f"/api/v1/bots/sessions/{sid}/summary")
    assert resp.status_code == 409
    assert fake_summary_agent.calls == 0


def test_summary_unknown_session_404(
    client: TestClient, fake_summary_agent: FakeBotSummaryAgent
) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000/summary"
    )
    assert resp.status_code == 404


def test_value_history_honours_resolution(
    client: TestClient, eligible_asset: Asset, db_session: Session
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    bot_id = uuid.UUID(sid)
    # Two intraday points in one hour; one daily snapshot.
    db_session.add_all(
        [
            BotValuePoint(
                bot_session_id=bot_id,
                captured_at=datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
                total_value=100.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
            BotValuePoint(
                bot_session_id=bot_id,
                captured_at=datetime(2026, 1, 6, 15, 30, tzinfo=UTC),
                total_value=105.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
            BotValueSnapshot(
                bot_session_id=bot_id,
                snapshot_date=date(2026, 1, 6),
                total_value=105.0,
                realised_pnl=0.0,
                unrealised_pnl=0.0,
            ),
        ]
    )
    db_session.flush()

    five = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history", params={"resolution": "5min"}
    )
    assert five.status_code == 200
    assert five.json()["resolution"] == "5min"
    assert len(five.json()["items"]) == 2
    assert "timestamp" in five.json()["items"][0]

    hourly = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history", params={"resolution": "hourly"}
    )
    assert len(hourly.json()["items"]) == 1
    assert hourly.json()["items"][0]["total_value"] == 105.0

    # Default resolution is daily (reads the snapshot curve, not the points).
    default = client.get(f"/api/v1/bots/sessions/{sid}/value-history")
    assert default.json()["resolution"] == "daily"
    assert len(default.json()["items"]) == 1


def test_value_history_rejects_unknown_resolution(
    client: TestClient, eligible_asset: Asset
) -> None:
    sid = client.post("/api/v1/bots/sessions", json=_create_payload()).json()[
        "id"
    ]
    resp = client.get(
        f"/api/v1/bots/sessions/{sid}/value-history",
        params={"resolution": "weekly"},
    )
    assert resp.status_code == 422


def test_value_history_unknown_session_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/bots/sessions/00000000-0000-0000-0000-000000000000/value-history"
    )
    assert resp.status_code == 404


def test_list_strategies(client: TestClient) -> None:
    resp = client.get("/api/v1/bots/strategies")
    assert resp.status_code == 200
    entries = {entry["key"]: entry for entry in resp.json()}
    assert "ma_crossover" in entries
    # The Donchian strategy is listed with its display name and params schema.
    donchian = entries["donchian_breakout"]
    assert donchian["display_name"] == "Donchian Range Breakout"
    assert donchian["explanation"]
    assert "version" in donchian["params_schema"]["properties"]
    # The Rolling-Average Reversion strategy is listed with its three axes.
    reversion = entries["rolling_average_reversion"]
    assert reversion["display_name"] == "Rolling-Average Reversion"
    assert reversion["explanation"]
    assert reversion["required_history"] == 20
    props = reversion["params_schema"]["properties"]
    assert {"average_type", "distance", "exit_mode", "window"} <= set(props)


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


def test_tick_flattens_stopped_orchestrator_bot_and_returns_its_cash(
    client: TestClient,
    db_session: Session,
    eligible_asset: Asset,
    stub_market_data: None,
    recording_notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence.bot_orchestrator import service as orchestrator_service
    from cadence.broker import get_broker
    from cadence.broker.stub import StubBroker
    from cadence.strategy_bots import service as bot_service
    from cadence.strategy_bots.constants import BotOrigin
    from cadence.strategy_bots.models import BotPosition

    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    broker = StubBroker()
    app.dependency_overrides[get_broker] = lambda: broker
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="Core", capital=10_000.0
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
    symbol = bot.symbols[0]
    bot.positions.append(
        BotPosition(
            asset_id=symbol.asset_id,
            ticker="AAPL",
            alpaca_symbol=symbol.alpaca_symbol,
            quantity=10,
            avg_price=100.0,
            opened_at=datetime(2026, 11, 10, 14, 0, tzinfo=UTC),
        )
    )
    bot.cash -= 1_000.0
    broker.buy("AAPL", 10)
    bot_service.stop_bot_session(db_session, bot.id)
    db_session.flush()

    resp = client.post("/api/v1/bots/tick", headers={"X-Cron-Token": "secret"})

    assert resp.status_code == 200
    assert resp.json()["flattened"] == 1
    db_session.refresh(bot)
    db_session.refresh(orchestrator)
    assert bot.positions == []
    assert bot.capital_returned_at is not None
    assert orchestrator.free_capital == pytest.approx(7_000.0 + bot.cash)


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


def test_snapshot_daily_rolls_orchestrator_bots_into_one_push(
    client: TestClient,
    db_session: Session,
    eligible_asset: Asset,
    recording_notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence.bot_orchestrator import service as orchestrator_service
    from cadence.bot_orchestrator.models import BotOrchestratorSnapshot
    from cadence.strategy_bots import service as bot_service
    from cadence.strategy_bots.constants import BotOrigin

    monkeypatch.setattr(settings, "REBALANCE_CRON_TOKEN", "secret")
    client.post("/api/v1/bots/sessions", json=_create_payload())  # a manual bot
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="Core rotation", capital=10_000.0
    )
    orchestrator.free_capital -= 3_000.0
    bot_service.create_bot_session(
        db_session,
        preset_key="ma_crossover_algo6",
        tickers=["AAPL"],
        initial_capital=3_000.0,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )
    db_session.flush()

    resp = client.post(
        "/api/v1/bots/snapshot-daily", headers={"X-Cron-Token": "secret"}
    )

    assert resp.status_code == 200
    assert resp.json() == {"snapshots": 2, "reconciled": 0, "orchestrator_snapshots": 1}
    titles = sorted(title or "" for _, title in recording_notifier.sent)
    assert len(titles) == 2
    assert titles[0].startswith("Cadence bot:")  # the manual bot
    assert titles[1] == "Cadence orchestrator: Core rotation daily P&L"
    assert (
        db_session.query(BotOrchestratorSnapshot)
        .filter(BotOrchestratorSnapshot.orchestrator_id == orchestrator.id)
        .count()
        == 1
    )
