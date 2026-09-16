"""Service tests for the AI-portfolio build and rebalance flows (stub broker).

Builds and rebalances now operate over the full asset universe with bounded
discovery, so these tests seed a universe first and inject a fake market-data
provider for discovery-adds. No network is touched.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session
from tests.fakes import (
    FakeAIPortfolioAgent,
    FakeMarketDataProvider,
    RecordingNotifier,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio.agent import (
    AIPortfolioBuildResult,
    AIPortfolioStock,
    AIRebalanceResult,
    AITargetAllocation,
)
from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.ai_portfolio.errors import AIPortfolioValidationError
from cadence.ai_portfolio.service import AIBuildParams
from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.broker.models import AssetClass, OrderType, TimeInForce
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import ScheduleMode
from cadence.portfolios import service as portfolios_service


class _ClosedBroker(StubBroker):
    def is_market_open(self) -> bool:
        return False


class _RecordingBroker(StubBroker):
    """StubBroker that records the ``asset_class`` used for each buy."""

    def __init__(self) -> None:
        super().__init__()
        self.buy_classes: dict[str, AssetClass] = {}

    def buy(
        self,
        symbol: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        asset_class: AssetClass = AssetClass.EQUITY,
    ):  # type: ignore[override]
        self.buy_classes[symbol] = asset_class
        return super().buy(
            symbol, quantity, order_type, limit_price, time_in_force, asset_class
        )


def _crypto_provider() -> FakeMarketDataProvider:
    """A provider yielding a crypto (``CRYPTOCURRENCY``) profile with no sector."""
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Bitcoin USD",
            exchange="CCC",
            currency="USD",
            price=60000.0,
            market_cap=1_000_000_000_000.0,
            quote_type="CRYPTOCURRENCY",
            sector_key=None,
        ),
        history=[
            HistoryBar(date=date(2015, 1, 1), close=300.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=60000.0, volume=1_000_000.0),
        ],
        fx_rates={"USD": 0.9},
    )


def _provider() -> FakeMarketDataProvider:
    """A market-data provider yielding one eligible-by-default asset profile."""
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


def _seed_universe(db_session: Session, *tickers: str) -> FakeMarketDataProvider:
    """Add the given tickers to the universe; return the provider used."""
    provider = _provider()
    for ticker in tickers:
        assets_service.add_asset(db_session, ticker, provider, StubBroker())
    return provider


def _build_result(*tickers: str) -> AIPortfolioBuildResult:
    picks = tickers or ("AAPL", "MSFT")
    weight = round(1.0 / len(picks), 4)
    return AIPortfolioBuildResult(
        portfolio_name="AI Growth",
        stocks=[
            AIPortfolioStock(
                ticker=t,
                company_name=t,
                allocation_pct=weight,
                investment_thesis="strong",
                confidence=0.8,
            )
            for t in picks
        ],
        overall_thesis="tech",
        risk_assessment="concentration",
    )


def _params(**kw: object) -> AIBuildParams:
    base: dict[str, object] = {"allocated_capital": 100_000.0}
    base.update(kw)
    return AIBuildParams(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def test_create_build_event_rejects_empty_universe(db_session: Session) -> None:
    with pytest.raises(AIPortfolioValidationError):
        service.create_build_event(db_session, _params())


def test_run_build_event_success_creates_portfolio_and_session(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    broker = StubBroker()
    event = service.create_build_event(db_session, _params(daily_rebalancing=True))

    service.run_build_event(db_session, event.id, agent, broker, provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert refreshed.event_type == EventType.BUILD.value
    assert refreshed.session_id is not None
    assert refreshed.portfolio_id is not None

    # The agent received the full enriched universe as candidates.
    assert agent.build_calls
    candidate_tickers = {c["ticker"] for c in agent.build_calls[0]["candidates"]}
    assert candidate_tickers == {"AAPL", "MSFT"}

    portfolio = portfolios_service.get_portfolio(db_session, refreshed.portfolio_id)
    assert portfolio.source == "ai_managed"
    assert portfolio.max_allocation_pct == 1.0
    assert set(portfolio.stocks) == {"AAPL", "MSFT"}

    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.strategy_key == "ai_buy_hold"
    assert session_row.schedule_mode == ScheduleMode.DAILY_REBALANCING.value

    trades = paper_service.get_session_trades(db_session, refreshed.session_id, limit=100)
    assert {t.ticker for t in trades} == {"AAPL", "MSFT"}

    runs = paper_service.get_session_runs(db_session, refreshed.session_id, limit=10)
    assert len(runs) == 1


def test_run_build_event_discovers_and_adds_new_asset(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    # The agent proposes a ticker (NVDA) that is not in the universe.
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value

    universe = {a.ticker for a in assets_service.list_assets(db_session)}
    assert "NVDA" in universe  # discovered ticker added to the universe

    portfolio = portfolios_service.get_portfolio(db_session, refreshed.portfolio_id)
    assert set(portfolio.stocks) == {"AAPL", "MSFT", "NVDA"}


def test_run_build_event_manual_schedule_when_not_enrolled(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params(daily_rebalancing=False))

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.schedule_mode == ScheduleMode.MANUAL.value


def test_run_build_event_failure_marks_event_failed(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_error=RuntimeError("agent boom"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.FAILED.value
    assert "boom" in (refreshed.error or "")


# --------------------------------------------------------------------------- #
# Rebalance
# --------------------------------------------------------------------------- #


def _seed_session(
    db_session: Session,
    broker: StubBroker,
    provider: FakeMarketDataProvider,
) -> tuple[object, object]:
    """Build a 3-holding AI session (AAPL, MSFT, NVDA) and return (session, portfolio)."""
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, daily_rebalancing=True)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    event = service.get_event(db_session, build_event.id)
    return event.session_id, event.portfolio_id


def test_run_rebalance_event_market_closed_is_skipped(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="x", target_allocations=[], portfolio_health="healthy"
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SKIPPED.value
    # Agent must not have been consulted while the market was closed.
    assert rebalance.rebalance_calls == []

    runs = paper_service.get_session_runs(db_session, session_id, limit=100)
    assert any(r.details and r.details[0].get("skipped") for r in runs)


def test_run_rebalance_event_trades_toward_targets_and_updates_stocks(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, portfolio_id = _seed_session(db_session, broker, provider)

    # Target only AAPL + MSFT -> NVDA is exited; end-state holdings drop NVDA.
    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="steady",
            target_allocations=[
                AITargetAllocation(
                    ticker="AAPL",
                    company_name="Apple",
                    allocation_pct=0.5,
                    investment_thesis="keep",
                    confidence=0.9,
                ),
                AITargetAllocation(
                    ticker="MSFT",
                    company_name="Microsoft",
                    allocation_pct=0.5,
                    investment_thesis="keep",
                    confidence=0.9,
                ),
            ],
            portfolio_health="healthy",
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert rebalance.rebalance_calls  # agent consulted while market open
    # The agent received the full universe as candidates.
    assert {c["ticker"] for c in rebalance.rebalance_calls[0]["candidates"]} == {
        "AAPL",
        "MSFT",
        "NVDA",
    }

    # NVDA fully exited -> a closed position recorded, and stocks updated.
    closed = paper_service.get_closed_positions(db_session, session_id, limit=100)
    assert any(c.ticker == "NVDA" for c in closed)

    portfolio = portfolios_service.get_portfolio(db_session, portfolio_id)
    assert set(portfolio.stocks) == {"AAPL", "MSFT"}


# --------------------------------------------------------------------------- #
# Crypto routing
# --------------------------------------------------------------------------- #


def test_run_build_event_routes_crypto_by_asset_class(db_session: Session) -> None:
    eq_provider = _seed_universe(db_session, "AAPL")
    assets_service.add_asset(db_session, "BTC-USD", _crypto_provider(), StubBroker())

    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "BTC-USD"))
    broker = _RecordingBroker()
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, broker, eq_provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    # The universe's asset class drove the per-ticker routing.
    assert broker.buy_classes["BTC-USD"] == AssetClass.CRYPTO
    assert broker.buy_classes["AAPL"] == AssetClass.EQUITY


def test_run_rebalance_event_closed_market_trades_crypto(db_session: Session) -> None:
    eq_provider = _seed_universe(db_session, "AAPL")
    assets_service.add_asset(db_session, "BTC-USD", _crypto_provider(), StubBroker())

    broker = _ClosedBroker()
    # Build a session holding AAPL + BTC-USD (build has no market guard).
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "BTC-USD"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, daily_rebalancing=True)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, eq_provider)
    session_id = service.get_event(db_session, build_event.id).session_id

    # Rebalance while the equities market is closed: target only crypto (AAPL is
    # untargeted -> would exit, but is skipped as an equity while closed).
    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="crypto up",
            target_allocations=[
                AITargetAllocation(
                    ticker="BTC-USD",
                    company_name="Bitcoin USD",
                    allocation_pct=1.0,
                    investment_thesis="momentum",
                    confidence=0.9,
                ),
            ],
            portfolio_health="healthy",
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, eq_provider)

    refreshed = service.get_event(db_session, rb_event.id)
    # The run was NOT skipped: crypto is tradable 24/7, so the agent was consulted.
    assert rebalance.rebalance_calls
    assert refreshed.status in (
        EventStatus.SUCCEEDED.value,
        EventStatus.PARTIAL.value,
    )

    trades = paper_service.get_session_trades(db_session, session_id, limit=100)
    rebalance_btc = [
        t
        for t in trades
        if t.ticker == "BTC-USD" and t.signal_type.startswith("ai_rebalance")
    ]
    assert rebalance_btc  # crypto traded while the equities market was closed

    # The equity was recorded as skipped (equity market closed), never traded in
    # this rebalance.
    rebalance_aapl = [
        t
        for t in trades
        if t.ticker == "AAPL" and t.signal_type.startswith("ai_rebalance")
    ]
    assert rebalance_aapl == []


def test_run_rebalance_event_closed_market_equity_only_is_skipped(
    db_session: Session,
) -> None:
    # Equity-only session with the market closed -> skipped run, no agent call.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="x", target_allocations=[], portfolio_health="healthy"
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SKIPPED.value
    assert rebalance.rebalance_calls == []


# --------------------------------------------------------------------------- #
# Daily-rebalance notifications
# --------------------------------------------------------------------------- #


def _rebalance_to_aapl_msft() -> FakeAIPortfolioAgent:
    """A rebalance agent targeting AAPL+MSFT (exits NVDA), so orders execute."""
    return FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="steady",
            target_allocations=[
                AITargetAllocation(
                    ticker="AAPL",
                    company_name="Apple",
                    allocation_pct=0.5,
                    investment_thesis="keep",
                    confidence=0.9,
                ),
                AITargetAllocation(
                    ticker="MSFT",
                    company_name="Microsoft",
                    allocation_pct=0.5,
                    investment_thesis="keep",
                    confidence=0.9,
                ),
            ],
            portfolio_health="healthy",
        )
    )


def test_run_rebalance_event_notifies_on_executed_orders(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    notifier = RecordingNotifier()

    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session,
        rb_event.id,
        _rebalance_to_aapl_msft(),
        broker,
        provider,
        notifier=notifier,
    )

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert "rebalanced" in title
    # NVDA is exited -> a SELL line names it; realized P&L is reported.
    assert "SELL" in message
    assert "NVDA" in message
    assert "Realized P&L" in message


def test_run_rebalance_event_notifies_on_failure(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    notifier = RecordingNotifier()

    rebalance = FakeAIPortfolioAgent(rebalance_error=RuntimeError("rebalance boom"))
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, rebalance, broker, provider, notifier=notifier
    )

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.FAILED.value
    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert "failed" in title
    assert "boom" in message


def test_run_rebalance_event_silent_on_market_closed_skip(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    notifier = RecordingNotifier()

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="x", target_allocations=[], portfolio_health="healthy"
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, rebalance, broker, provider, notifier=notifier
    )

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SKIPPED.value
    # A skipped run (nothing executed) must not push a notification.
    assert notifier.sent == []


def test_run_rebalance_event_notifier_failure_does_not_fail_rebalance(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    notifier = RecordingNotifier(raises=True)

    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session,
        rb_event.id,
        _rebalance_to_aapl_msft(),
        broker,
        provider,
        notifier=notifier,
    )

    refreshed = service.get_event(db_session, rb_event.id)
    # The notifier raised, but the rebalance still succeeded.
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert len(notifier.sent) == 1


def test_run_rebalance_event_no_notifier_is_silent(db_session: Session) -> None:
    # Manual path: no notifier supplied -> no notification, no error.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, _rebalance_to_aapl_msft(), broker, provider
    )

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value


def test_get_inflight_rebalance_event(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    assert service.get_inflight_rebalance_event(db_session, session_id) is None
    rb_event = service.create_rebalance_event(db_session, session_id)
    inflight = service.get_inflight_rebalance_event(db_session, session_id)
    assert inflight is not None
    assert inflight.id == rb_event.id


# --------------------------------------------------------------------------- #
# Audit trail: run ↔ trade/position links and research persistence
# --------------------------------------------------------------------------- #


def test_run_build_event_stamps_event_id_and_persists_research(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(
        build_result=_build_result("AAPL", "MSFT"),
        research_queries=["AAPL outlook", "MSFT outlook"],
    )
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    # The research transcript is persisted on the event.
    assert refreshed.research is not None
    assert [r["query"] for r in refreshed.research] == [
        "AAPL outlook",
        "MSFT outlook",
    ]

    # Every opening trade references the run that produced it.
    trades = paper_service.get_trades_by_event(db_session, event.id)
    assert {t.ticker for t in trades} == {"AAPL", "MSFT"}
    assert all(t.ai_portfolio_event_id == event.id for t in trades)


def test_run_build_event_persists_partial_research_on_failure(
    db_session: Session,
) -> None:
    # The agent researches, then fails: the research captured before the failure
    # must still be persisted on the (failed) event.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(
        build_error=RuntimeError("agent boom"),
        research_queries=["searched before crash"],
    )
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.FAILED.value
    assert refreshed.research is not None
    assert [r["query"] for r in refreshed.research] == ["searched before crash"]


def test_run_rebalance_event_stamps_event_id_on_trades_and_closed_positions(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = _rebalance_to_aapl_msft()
    rebalance._research_queries = ["market check"]  # emit one research entry
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert refreshed.research is not None
    assert [r["query"] for r in refreshed.research] == ["market check"]

    # NVDA exit -> a closed position linked to this rebalance event.
    closed = paper_service.get_closed_positions_by_event(db_session, rb_event.id)
    assert any(c.ticker == "NVDA" for c in closed)
    assert all(c.ai_portfolio_event_id == rb_event.id for c in closed)

    # Opening trades from the rebalance also reference the event.
    trades = paper_service.get_trades_by_event(db_session, rb_event.id)
    assert trades
    assert all(t.ai_portfolio_event_id == rb_event.id for t in trades)


def test_skipped_rebalance_records_no_research(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="x", target_allocations=[], portfolio_health="healthy"
        ),
        research_queries=["should never run"],
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SKIPPED.value
    # The agent was never consulted, so no research was captured.
    assert rebalance.rebalance_calls == []
    assert refreshed.research is None


def test_list_and_count_ai_runs_across_sessions(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)  # one build event
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, _rebalance_to_aapl_msft(), broker, provider
    )

    # Both the build and the rebalance are listed, newest first.
    runs = service.list_ai_runs(db_session)
    assert len(runs) == 2
    assert runs[0].created_at >= runs[1].created_at
    assert service.count_ai_runs(db_session) == 2

    # Filter by event type.
    builds = service.list_ai_runs(db_session, event_type=EventType.BUILD)
    assert [e.event_type for e in builds] == [EventType.BUILD.value]
    assert service.count_ai_runs(db_session, event_type=EventType.REBALANCE) == 1

    # Filter by status.
    succeeded = service.count_ai_runs(db_session, status=EventStatus.SUCCEEDED)
    assert succeeded == 2
