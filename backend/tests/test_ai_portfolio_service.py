"""Service tests for the AI-portfolio build and rebalance flows (stub broker).

Builds and rebalances now operate over the full asset universe with bounded
discovery, so these tests seed a universe first and inject a fake market-data
provider for discovery-adds. No network is touched.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from agents.exceptions import MaxTurnsExceeded
from sqlalchemy import select
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
from cadence.ai_portfolio.constants import (
    TREND_PROMPT_VERSION,
    EventStatus,
    EventType,
)
from cadence.ai_portfolio.errors import (
    AIPortfolioValidationError,
    RebalancePromptNotFoundError,
    SessionNotEligibleError,
)
from cadence.ai_portfolio.models import AIPortfolioEvent, RebalancePrompt
from cadence.ai_portfolio.service import AIBuildParams
from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.assets.models import Asset
from cadence.broker.models import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    Quote,
    TimeInForce,
)
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import (
    STOP_LOSS_RUN_TRIGGER,
    STOP_LOSS_SIGNAL_TYPE,
    Benchmark,
    ScheduleMode,
    SessionStatus,
)
from cadence.paper_trading.models import BenchmarkPrice, StopLossQuarantine
from cadence.portfolios import service as portfolios_service
from cadence.technical_indicators.models import TechnicalIndicator


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


class _StopLossBroker(StubBroker):
    """StubBroker whose scan quotes and market status are controllable.

    ``overrides`` maps a ticker to the price the batched ``get_quotes`` should
    report for it (a ``None`` value yields a price-less quote so the scan skips it,
    simulating a missing quote); tickers absent from the map keep the deterministic
    stub price. ``market_open`` drives the equity market-status guard.
    """

    def __init__(
        self,
        *,
        overrides: dict[str, float | None] | None = None,
        market_open: bool = True,
        initial_cash: float = 1_000_000.0,
    ) -> None:
        super().__init__(initial_cash=initial_cash)
        self._overrides = overrides or {}
        self._market_open = market_open

    def set_overrides(self, overrides: dict[str, float | None]) -> None:
        self._overrides = overrides

    def set_market_open(self, is_open: bool) -> None:
        self._market_open = is_open

    def is_market_open(self) -> bool:
        return self._market_open

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        result: dict[str, Quote] = {}
        for symbol in symbols:
            if symbol in self._overrides:
                price = self._overrides[symbol]
                result[symbol] = Quote(
                    symbol=symbol,
                    bid=price,
                    ask=price,
                    last=price,
                    volume=1_000,
                    timestamp=datetime.now(UTC),
                )
            else:
                result[symbol] = self.get_quote(symbol)
        return result


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
            currency="USD",
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


def test_ai_build_params_guardrails_round_trip() -> None:
    # The frozen guardrail config must survive to_payload -> from_payload exactly.
    params = AIBuildParams(
        allocated_capital=50_000.0,
        risk_guardrails_enabled=True,
        max_allocation_pct=0.25,
        max_asset_class_pct=0.6,
        min_positions=5,
        max_invested_pct=0.9,
    )
    restored = AIBuildParams.from_payload(params.to_payload())
    assert restored == params
    assert restored.risk_guardrails_enabled is True
    assert restored.max_allocation_pct == 0.25
    assert restored.max_asset_class_pct == 0.6
    assert restored.min_positions == 5
    assert restored.max_invested_pct == 0.9


def test_run_build_event_freezes_guardrails_and_caps_trades(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    broker = StubBroker()
    # Per-asset cap 0.25 with class/invested caps neutral isolates the per-asset
    # clamp: each 0.5 target is clamped to 0.25 with no uncapped name to absorb the
    # excess, so the rest stays cash.
    event = service.create_build_event(
        db_session,
        _params(
            allocated_capital=50_000.0,
            risk_guardrails_enabled=True,
            max_allocation_pct=0.25,
            max_asset_class_pct=1.0,
            min_positions=2,
            max_invested_pct=1.0,
        ),
    )

    service.run_build_event(db_session, event.id, agent, broker, provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value

    # The advisory caps were handed to the AI.
    assert agent.build_calls[0]["guardrails"] is not None

    # The frozen guardrail config is persisted on the session and portfolio.
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.risk_guardrails_enabled is True
    assert session_row.max_allocation_pct == 0.25
    assert session_row.max_asset_class_pct == 1.0
    assert session_row.min_positions == 2
    assert session_row.max_invested_pct == 1.0
    portfolio = portfolios_service.get_portfolio(db_session, refreshed.portfolio_id)
    assert portfolio.max_allocation_pct == 0.25

    # Trades are sized off the capped 0.25 weight, not the AI's raw 0.5.
    trades = {
        t.ticker: t
        for t in paper_service.get_session_trades(
            db_session, refreshed.session_id, limit=100
        )
    }
    aapl_price = broker.get_quote("AAPL").last
    msft_price = broker.get_quote("MSFT").last
    assert trades["AAPL"].quantity == int(0.25 * 50_000 / aapl_price)
    assert trades["MSFT"].quantity == int(0.25 * 50_000 / msft_price)


def test_run_build_event_records_min_positions_observation(
    db_session: Session,
) -> None:
    # The AI returns 2 names but the guardrails require 5; min positions is not
    # fixable by clamping, so the shortfall is recorded and the build still succeeds.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(
        db_session,
        _params(
            allocated_capital=50_000.0,
            risk_guardrails_enabled=True,
            max_allocation_pct=0.5,
            max_asset_class_pct=1.0,
            min_positions=5,
            max_invested_pct=1.0,
        ),
    )

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    observation = refreshed.run_stats["guardrails"]["min_positions"]
    assert observation == {"required": 5, "returned": 2, "shortfall": 3}


def test_run_build_event_guardrails_off_keeps_no_op_config(
    db_session: Session,
) -> None:
    # A default (guardrails-off) build leaves the session no-op: disabled flag,
    # null params, and the max_allocation_pct 1.0 default untouched.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.risk_guardrails_enabled is False
    assert session_row.max_allocation_pct == 1.0
    assert session_row.max_asset_class_pct is None
    assert session_row.min_positions is None
    assert session_row.max_invested_pct is None
    assert agent.build_calls[0]["guardrails"] is None
    assert (refreshed.run_stats or {}).get("guardrails") is None


def test_run_build_event_persists_run_stats(db_session: Session) -> None:
    # The machine-readable run_stats payload is captured for later offline learning
    # (never surfaced in the API/UI): order counts + per-trade details incl. the
    # filled price that actions_taken deliberately drops.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    stats = refreshed.run_stats
    assert stats is not None
    assert stats["orders"]["executed"] == 2
    assert stats["orders"]["skipped"] == 0
    assert stats["orders"]["total"] == 2
    assert stats["orders"]["all_executed"] is True
    trades = stats["trades"]
    assert {t["ticker"] for t in trades} == {"AAPL", "MSFT"}
    # filled_price is present in run_stats but omitted from the UI-facing payload.
    assert all("filled_price" in t for t in trades)
    assert all("filled_price" not in a for a in refreshed.actions_taken)


def test_run_rebalance_event_run_stats_includes_pnl_and_account(
    db_session: Session,
) -> None:
    # A rebalance additionally records realized P&L and an account/valuation
    # snapshot in run_stats (the build path omits these).
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

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
    stats = refreshed.run_stats
    assert stats is not None
    assert "orders" in stats and "trades" in stats
    assert "realized_pnl" in stats
    assert "account" in stats


def _single_target(ticker: str, pct: float) -> AIRebalanceResult:
    return AIRebalanceResult(
        evaluation_summary="ok",
        target_allocations=[
            AITargetAllocation(
                ticker=ticker,
                company_name=ticker,
                allocation_pct=pct,
                investment_thesis="conviction",
                confidence=0.9,
            )
        ],
        portfolio_health="healthy",
    )


def test_run_rebalance_event_clamps_target_over_cap(db_session: Session) -> None:
    # Session frozen with a 0.5 per-asset cap; a 0.5-cap build lands the 3 names
    # under the cap (~0.333 each). The AI then targets AAPL=1.0, which the frozen
    # cap clamps to 0.5 so AAPL is bought up to 0.5 — not the full 1.0.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(
        db_session,
        broker,
        provider,
        risk_guardrails_enabled=True,
        max_allocation_pct=0.5,
        max_asset_class_pct=1.0,
        min_positions=1,
        max_invested_pct=1.0,
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_single_target("AAPL", 1.0))
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    # The caps were read back off the frozen session and handed to the agent.
    assert rebalance.rebalance_calls[0]["guardrails"] is not None

    price = broker.get_quote("AAPL").last
    aapl = paper_service.get_open_position(db_session, session_id, "AAPL")
    assert aapl is not None
    # Clamped to the 0.5 cap, strictly below the un-clamped 1.0 target.
    assert aapl.quantity == pytest.approx(int(50_000 * 0.5 / price))
    assert aapl.quantity < int(50_000 * 1.0 / price)
    # The other names are exited (target vector held only AAPL).
    assert paper_service.get_open_position(db_session, session_id, "MSFT") is None


def test_run_rebalance_event_opted_out_is_unclamped(db_session: Session) -> None:
    # A session built without guardrails applies no caps at rebalance: an AAPL=1.0
    # target sizes to the full allocation.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = FakeAIPortfolioAgent(rebalance_result=_single_target("AAPL", 1.0))
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls[0]["guardrails"] is None
    price = broker.get_quote("AAPL").last
    aapl = paper_service.get_open_position(db_session, session_id, "AAPL")
    assert aapl is not None
    assert aapl.quantity == pytest.approx(int(50_000 * 1.0 / price))


def test_run_build_event_generates_distinct_portfolio_name(
    db_session: Session,
) -> None:
    # The build must NOT use the AI's generic name; it generates a distinct,
    # human-friendly name prefixed with the risk profile.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(
        db_session, _params(risk_profile="aggressive")
    )

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.portfolio_id is not None
    portfolio = portfolios_service.get_portfolio(db_session, refreshed.portfolio_id)
    # Not the AI-provided name, and carries the risk-profile prefix.
    assert portfolio.name != "AI Growth"
    assert portfolio.name.startswith("Aggressive ")
    # The AI's thesis is still preserved as the description.
    assert portfolio.description == "tech"


def test_run_build_event_name_is_unique_against_existing(
    db_session: Session,
) -> None:
    # Two consecutive builds must not collide on the generated name.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))

    first_event = service.create_build_event(db_session, _params())
    service.run_build_event(db_session, first_event.id, agent, StubBroker(), provider)
    first = portfolios_service.get_portfolio(
        db_session, service.get_event(db_session, first_event.id).portfolio_id
    )

    second_event = service.create_build_event(db_session, _params())
    service.run_build_event(db_session, second_event.id, agent, StubBroker(), provider)
    second = portfolios_service.get_portfolio(
        db_session, service.get_event(db_session, second_event.id).portfolio_id
    )

    assert first.name != second.name


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


def _seed_mixed_universe(db_session: Session) -> None:
    """Seed one stock (AAPL) and one crypto (BTC-USD) into the universe."""
    assets_service.add_asset(db_session, "AAPL", _provider(), StubBroker())
    assets_service.add_asset(db_session, "BTC-USD", _crypto_provider(), StubBroker())


def test_run_build_event_scope_restricts_candidates_and_persists_scope(
    db_session: Session,
) -> None:
    _seed_mixed_universe(db_session)
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL"))
    # stocks-only scope: the crypto asset must not appear as a candidate.
    event = service.create_build_event(db_session, _params(asset_types="stocks"))

    service.run_build_event(db_session, event.id, agent, StubBroker(), _provider())

    assert agent.build_calls
    candidate_tickers = {c["ticker"] for c in agent.build_calls[0]["candidates"]}
    assert candidate_tickers == {"AAPL"}  # BTC-USD (crypto) excluded

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.session_metadata["asset_types"] == "stocks"


def test_run_build_event_rejects_out_of_scope_discovery(
    db_session: Session,
) -> None:
    # crypto-only scope; the equity provider classifies any discovered ticker as a
    # stock, which is outside scope and must not enter the universe.
    assets_service.add_asset(db_session, "BTC-USD", _crypto_provider(), StubBroker())
    agent = FakeAIPortfolioAgent(build_result=_build_result("TSLA"))
    event = service.create_build_event(db_session, _params(asset_types="crypto"))

    service.run_build_event(db_session, event.id, agent, StubBroker(), _provider())

    universe = {a.ticker for a in assets_service.list_assets(db_session)}
    assert "TSLA" not in universe  # out-of-scope stock rejected by the hard-filter


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


def test_run_build_event_humanizes_max_turns_error(db_session: Session) -> None:
    # The agents SDK raises a terse "Max turns (N) exceeded"; the service persists
    # an actionable message instead of the raw string.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(
        build_error=MaxTurnsExceeded("Max turns (12) exceeded")
    )
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.FAILED.value
    error = refreshed.error or ""
    assert "step limit" in error
    assert "Max turns (12) exceeded" not in error


# --------------------------------------------------------------------------- #
# Rebalance
# --------------------------------------------------------------------------- #


def _seed_session(
    db_session: Session,
    broker: StubBroker,
    provider: FakeMarketDataProvider,
    **build_params: object,
) -> tuple[object, object]:
    """Build a 3-holding AI session (AAPL, MSFT, NVDA) and return (session, portfolio).

    Extra ``build_params`` (e.g. ``risk_profile``/``asset_types``) are forwarded to
    the build params so callers can seed a scoped or non-default-risk session.
    """
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    params = {"allocated_capital": 50_000.0, "daily_rebalancing": True}
    params.update(build_params)
    build_event = service.create_build_event(db_session, _params(**params))
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


def _flat_rebalance_result() -> AIRebalanceResult:
    return AIRebalanceResult(
        evaluation_summary="ok",
        target_allocations=[
            AITargetAllocation(
                ticker="AAPL",
                company_name="Apple",
                allocation_pct=1.0,
                investment_thesis="keep",
                confidence=0.9,
            )
        ],
        portfolio_health="healthy",
    )


def test_get_active_rebalance_prompt_returns_highest_version(
    db_session: Session,
) -> None:
    # conftest seeds version 1; a newer version supersedes it as the active prompt.
    db_session.add(
        RebalancePrompt(
            version=2,
            instructions="v2 instructions",
            input_template="v2 input {risk_profile}",
        )
    )
    db_session.flush()

    active = service.get_active_rebalance_prompt(db_session)
    assert active.version == 2
    assert active.instructions == "v2 instructions"


def test_run_build_event_freezes_active_prompt_version(db_session: Session) -> None:
    # A higher version is active at build time, so the session must freeze it.
    db_session.add(
        RebalancePrompt(
            version=7,
            instructions="v7 instructions {max_new_assets}",
            input_template="v7 input {risk_profile}",
        )
    )
    db_session.flush()

    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.rebalance_prompt_version == 7


def test_run_rebalance_event_uses_frozen_version(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Build freezes the conftest-seeded active version (1) onto the session.
    session_id, _ = _seed_session(db_session, broker, provider)
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.rebalance_prompt_version == 1

    # A newer version becomes active AFTER the build; the frozen v1 must still win.
    db_session.add(
        RebalancePrompt(
            version=99,
            instructions="ACTIVE instructions {max_new_assets}",
            input_template="ACTIVE input {risk_profile} {candidates_json}",
        )
    )
    db_session.flush()

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    call = rebalance.rebalance_calls[0]
    # The service passes the session's FROZEN (v1, conftest seed) templates through,
    # not the now-active v99; placeholder rendering happens inside the real agent.
    assert call["instructions"].startswith("Rebalance instructions (test seed).")
    assert call["input_template"].startswith("Rebalance {risk_profile} portfolio.")


def test_run_rebalance_event_fails_when_frozen_version_missing(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    # Delete the session's frozen prompt version so it can no longer be resolved,
    # even though other versions may exist.
    frozen = paper_service.get_session(db_session, session_id).rebalance_prompt_version
    db_session.query(RebalancePrompt).filter_by(version=frozen).delete()
    db_session.flush()

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.FAILED.value
    assert "prompt" in (refreshed.error or "").lower()
    # The agent is never consulted without a resolvable prompt.
    assert rebalance.rebalance_calls == []


def test_get_rebalance_prompt_by_version_returns_row(db_session: Session) -> None:
    db_session.add(
        RebalancePrompt(
            version=5,
            instructions="v5 instructions",
            input_template="v5 input {risk_profile}",
        )
    )
    db_session.flush()

    prompt = service.get_rebalance_prompt_by_version(db_session, 5)
    assert prompt.version == 5
    assert prompt.instructions == "v5 instructions"


def test_get_rebalance_prompt_by_version_raises_when_unknown(
    db_session: Session,
) -> None:
    with pytest.raises(RebalancePromptNotFoundError):
        service.get_rebalance_prompt_by_version(db_session, 12345)


def _load_migration(filename: str) -> object:
    """Import a migration module by filename from ``backend/migrations/versions``."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1] / "migrations" / "versions" / filename
    )
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebalance_prompt_v2_seed_describes_transaction_cost() -> None:
    # The shipped version-2 seed must inform the agent of the per-trade cost and
    # keep version 1's input template verbatim (only the instructions change).
    v1 = _load_migration("a1d4e7c2b9f8_add_rebalance_prompt_table.py")
    v2 = _load_migration("d4b7e2f9a1c6_add_total_fees_and_rebalance_prompt_v2.py")

    instructions = v2._V2_INSTRUCTIONS.lower()
    assert "transaction cost" in instructions
    assert "churn" in instructions
    # Runtime placeholders are preserved so the renderer still fills them.
    assert "{max_new_assets}" in v2._V2_INSTRUCTIONS
    assert "{max_web_searches}" in v2._V2_INSTRUCTIONS
    # Input template is unchanged from version 1.
    assert v2._V2_INPUT_TEMPLATE == v1._SEED_INPUT_TEMPLATE


def test_get_active_rebalance_prompt_raises_when_empty(db_session: Session) -> None:
    db_session.query(RebalancePrompt).delete()
    db_session.flush()
    with pytest.raises(RebalancePromptNotFoundError):
        service.get_active_rebalance_prompt(db_session)


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


def _noop_rebalance() -> FakeAIPortfolioAgent:
    """A rebalance agent that keeps every holding (empty targets = no-op-ish)."""
    return FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="steady",
            target_allocations=[
                AITargetAllocation(
                    ticker=t,
                    company_name=t,
                    allocation_pct=round(1 / 3, 4),
                    investment_thesis="keep",
                    confidence=0.9,
                )
                for t in ("AAPL", "MSFT", "NVDA")
            ],
            portfolio_health="healthy",
        )
    )


def test_run_rebalance_event_applies_persisted_risk_profile(
    db_session: Session,
) -> None:
    # A session built as aggressive must rebalance as aggressive — the profile is
    # read back from session_metadata and passed to the agent (bug fix).
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(
        db_session, broker, provider, risk_profile="aggressive"
    )

    rebalance = _noop_rebalance()
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    assert rebalance.rebalance_calls[0]["risk_profile"] == "aggressive"


def test_run_rebalance_event_legacy_session_defaults_risk_and_scope(
    db_session: Session,
) -> None:
    # A session whose metadata predates these fields is treated as balanced/both.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    # Simulate a legacy session: strip the two fields from session_metadata.
    session_row = paper_service.get_session(db_session, session_id)
    metadata = dict(session_row.session_metadata or {})
    metadata.pop("risk_profile", None)
    metadata.pop("asset_types", None)
    session_row.session_metadata = metadata
    db_session.commit()

    rebalance = _noop_rebalance()
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    call = rebalance.rebalance_calls[0]
    assert call["risk_profile"] == "balanced"
    # both-scope => the full universe (seeded + discovered NVDA) is offered.
    assert {c["ticker"] for c in call["candidates"]} == {"AAPL", "MSFT", "NVDA"}


def test_run_rebalance_event_scope_restricts_candidates(
    db_session: Session,
) -> None:
    # A crypto-only session's rebalance must only offer crypto candidates even
    # though the universe also holds stocks.
    _seed_mixed_universe(db_session)
    broker = StubBroker()
    # Build a crypto-only session holding BTC-USD.
    agent = FakeAIPortfolioAgent(build_result=_build_result("BTC-USD"))
    build_event = service.create_build_event(
        db_session, _params(asset_types="crypto")
    )
    service.run_build_event(db_session, build_event.id, agent, broker, _crypto_provider())
    session_id = service.get_event(db_session, build_event.id).session_id

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="steady",
            target_allocations=[
                AITargetAllocation(
                    ticker="BTC-USD",
                    company_name="Bitcoin",
                    allocation_pct=1.0,
                    investment_thesis="keep",
                    confidence=0.9,
                )
            ],
            portfolio_health="healthy",
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, rebalance, broker, _crypto_provider()
    )

    assert rebalance.rebalance_calls
    candidate_tickers = {c["ticker"] for c in rebalance.rebalance_calls[0]["candidates"]}
    assert candidate_tickers == {"BTC-USD"}  # AAPL (stock) excluded from scope


# --------------------------------------------------------------------------- #
# Close (full liquidation)
# --------------------------------------------------------------------------- #


def test_close_session_liquidates_all_positions_and_stops(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    assert broker.get_positions()  # sanity: the build opened positions

    event = service.close_session(db_session, session_id, broker)

    assert event.event_type == EventType.CLOSE.value
    assert event.status == EventStatus.SUCCEEDED.value

    # The session is stopped so it drops out of rebalance + daily fan-out.
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.status == SessionStatus.STOPPED.value

    # Every held ticker was sold and recorded as a closed position, and the broker
    # holds nothing afterwards.
    closed = paper_service.get_closed_positions(db_session, session_id, limit=100)
    assert {c.ticker for c in closed} == {"AAPL", "MSFT", "NVDA"}
    assert broker.get_positions() == []

    # Liquidation trades link back to the close event and are tagged ai_close_*.
    trades = paper_service.get_trades_by_event(db_session, event.id)
    assert {t.ticker for t in trades} == {"AAPL", "MSFT", "NVDA"}
    assert all(t.signal_type == "ai_close_sell" for t in trades)


def test_close_session_liquidates_equities_when_market_closed(
    db_session: Session,
) -> None:
    # A close ignores market hours: equities are sold even when closed.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    event = service.close_session(db_session, session_id, broker)

    assert event.status == EventStatus.SUCCEEDED.value
    closed = paper_service.get_closed_positions(db_session, session_id, limit=100)
    assert {c.ticker for c in closed} == {"AAPL", "MSFT", "NVDA"}


def test_close_session_rejects_non_ai_session(db_session: Session) -> None:
    portfolio = portfolios_service.create_portfolio(
        db_session, name="Manual", stocks=["AAPL"]
    )
    session_row = paper_service.create_session(
        db_session, portfolio_id=portfolio.id, strategy_key="momentum", rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    with pytest.raises(SessionNotEligibleError):
        service.close_session(db_session, session_row.id, StubBroker())


def test_close_session_rejects_already_stopped_session(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    service.close_session(db_session, session_id, broker)  # first close -> stopped
    with pytest.raises(SessionNotEligibleError):
        service.close_session(db_session, session_id, broker)


# --------------------------------------------------------------------------- #
# Position ledger
# --------------------------------------------------------------------------- #


def test_run_build_event_opens_ledger_rows(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    ledger = {
        p.ticker: p
        for p in paper_service.list_open_positions(db_session, session_id)
    }
    trades = {
        t.ticker: t
        for t in paper_service.get_session_trades(db_session, session_id, limit=100)
    }
    assert set(ledger) == {"AAPL", "MSFT", "NVDA"}
    for ticker, entry in ledger.items():
        # One ledger row per bought ticker with the trade's quantity and the
        # fill price as its cost basis.
        assert entry.quantity == pytest.approx(trades[ticker].quantity)
        assert entry.avg_cost == pytest.approx(trades[ticker].filled_price)


def test_rebalance_realized_pnl_uses_ledger_basis(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    # Force a known low entry basis on NVDA in the ledger, then exit it.
    nvda = paper_service.get_open_position(db_session, session_id, "NVDA")
    assert nvda is not None
    nvda.avg_cost = 1.0
    db_session.commit()
    qty = nvda.quantity

    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(
        db_session, rb_event.id, _rebalance_to_aapl_msft(), broker, provider
    )

    closed = [
        c
        for c in paper_service.get_closed_positions(db_session, session_id, limit=100)
        if c.ticker == "NVDA"
    ]
    assert len(closed) == 1
    # Entry price is the ledger's avg cost, not the broker's blended average.
    assert closed[0].entry_price == pytest.approx(1.0)
    exit_price = broker.get_quote("NVDA").last
    assert exit_price is not None
    assert closed[0].realized_pnl == pytest.approx((exit_price - 1.0) * qty)


def test_close_realized_pnl_uses_ledger_basis(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    for entry in paper_service.list_open_positions(db_session, session_id):
        entry.avg_cost = 1.0
    db_session.commit()

    event = service.close_session(db_session, session_id, broker)
    assert event.status == EventStatus.SUCCEEDED.value

    closed = paper_service.get_closed_positions(db_session, session_id, limit=100)
    assert closed
    assert all(c.entry_price == pytest.approx(1.0) for c in closed)
    assert all(c.realized_pnl > 0 for c in closed)  # exit price >> $1 basis


def test_close_empties_ledger(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    ledger_before = {
        p.ticker for p in paper_service.list_open_positions(db_session, session_id)
    }
    assert ledger_before == {"AAPL", "MSFT", "NVDA"}

    service.close_session(db_session, session_id, broker)

    # Exactly the ledger's open positions are closed, and the ledger is emptied.
    closed = {
        c.ticker
        for c in paper_service.get_closed_positions(db_session, session_id, limit=100)
    }
    assert closed == ledger_before
    assert paper_service.list_open_positions(db_session, session_id) == []


def test_rebalance_deltas_isolated_per_session_ledger(db_session: Session) -> None:
    # Two sessions hold AAPL in the same account-wide broker. A rebalance of one
    # must compute its delta from that session's own ledger, not the combined
    # broker position.
    provider = _seed_universe(db_session, "AAPL")
    broker = StubBroker()

    ev_a = service.create_build_event(db_session, _params(allocated_capital=30_000.0))
    service.run_build_event(
        db_session, ev_a.id, FakeAIPortfolioAgent(build_result=_build_result("AAPL")),
        broker, provider,
    )
    session_a = service.get_event(db_session, ev_a.id).session_id

    ev_b = service.create_build_event(db_session, _params(allocated_capital=60_000.0))
    service.run_build_event(
        db_session, ev_b.id, FakeAIPortfolioAgent(build_result=_build_result("AAPL")),
        broker, provider,
    )
    session_b = service.get_event(db_session, ev_b.id).session_id

    a_aapl = paper_service.get_open_position(db_session, session_a, "AAPL")
    b_aapl = paper_service.get_open_position(db_session, session_b, "AAPL")
    assert a_aapl is not None and b_aapl is not None
    # Each session's ledger tracks its own quantity, not the shared account total.
    assert a_aapl.quantity < b_aapl.quantity

    # Rebalance A back to 100% AAPL at the same capital: target == A's own holding,
    # so the delta is zero. Reading the account-wide broker position (A+B) would
    # over-count and trigger a spurious SELL.
    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="hold",
            target_allocations=[
                AITargetAllocation(
                    ticker="AAPL",
                    company_name="Apple",
                    allocation_pct=1.0,
                    investment_thesis="keep",
                    confidence=0.9,
                )
            ],
            portfolio_health="healthy",
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_a)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    rebalance_aapl = [
        t
        for t in paper_service.get_session_trades(db_session, session_a, limit=100)
        if t.ticker == "AAPL" and t.signal_type.startswith("ai_rebalance")
    ]
    assert rebalance_aapl == []  # no delta -> no cross-contamination trade
    after = paper_service.get_open_position(db_session, session_a, "AAPL")
    assert after is not None
    assert after.quantity == pytest.approx(a_aapl.quantity)


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


# --------------------------------------------------------------------------- #
# Daily value snapshots + Pushover report
# --------------------------------------------------------------------------- #


def _held_ai_session(
    db_session: Session, name: str, ticker: str
) -> object:
    """An active AI session holding one open ledger position."""
    portfolio = portfolios_service.create_portfolio(
        db_session, name=name, stocks=[ticker]
    )
    sess = paper_service.create_session(
        db_session,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        allocated_capital=100_000.0, rebalance_prompt_version=1, benchmark=Benchmark.SP500)
    paper_service.apply_fill_to_ledger(
        db_session,
        session_id=sess.id,
        ticker=ticker,
        side=OrderSide.BUY,
        shares=10,
        price=100.0,
    )
    return sess


def test_snapshot_all_sessions_targets_only_active_ai(db_session: Session) -> None:
    broker = StubBroker()
    notifier = RecordingNotifier()

    ai_active = _held_ai_session(db_session, "AI Growth", "AAPL")

    # A non-AI active session must be ignored.
    non_ai_portfolio = portfolios_service.create_portfolio(
        db_session, name="Manual", stocks=["MSFT"]
    )
    paper_service.create_session(
        db_session,
        portfolio_id=non_ai_portfolio.id,
        strategy_key="momentum", rebalance_prompt_version=1, benchmark=Benchmark.SP500)

    # A stopped AI session must be ignored (not active).
    stopped = _held_ai_session(db_session, "AI Retired", "TSLA")
    paper_service.update_session_status(
        db_session, stopped.id, SessionStatus.STOPPED
    )

    ids = service.snapshot_all_sessions(
        db_session, broker=broker, notifier=notifier, as_of=date(2026, 1, 5)
    )

    assert ids == [ai_active.id]
    # Exactly one snapshot persisted, for the active AI session.
    snaps = paper_service.list_value_snapshots(db_session, session_id=ai_active.id)
    assert len(snaps) == 1
    # One per-session report was sent: the portfolio name titles it and the body
    # carries the headline KPIs plus that session's best/worst holding.
    assert len(notifier.sent) == 1
    message, title = notifier.sent[0]
    assert title == "Cadence: AI Growth daily P&L"
    assert "Total return:" in message
    assert "Sharpe:" in message
    assert "Best:" in message and "Worst:" in message
    assert "AAPL" in message


def test_snapshot_all_sessions_survives_notifier_failure(
    db_session: Session,
) -> None:
    broker = StubBroker()
    notifier = RecordingNotifier(raises=True)
    ai_active = _held_ai_session(db_session, "AI Growth", "AAPL")

    # A raising notifier must not fail the job; snapshots still persist.
    ids = service.snapshot_all_sessions(
        db_session, broker=broker, notifier=notifier, as_of=date(2026, 1, 5)
    )

    assert ids == [ai_active.id]
    assert len(notifier.sent) == 1  # send was attempted (and raised)
    snaps = paper_service.list_value_snapshots(db_session, session_id=ai_active.id)
    assert len(snaps) == 1


# --------------------------------------------------------------------------- #
# Build benchmark selection (7.1) + daily-report comparison (8.1)
# --------------------------------------------------------------------------- #


def test_run_build_event_defaults_benchmark_to_sp500(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())  # benchmark omitted

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.benchmark == Benchmark.SP500.value


def test_run_build_event_uses_supplied_benchmark(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params(benchmark="DJIA"))

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.benchmark == Benchmark.DJIA.value


def test_snapshot_report_includes_benchmark_comparison(db_session: Session) -> None:
    broker = StubBroker()
    notifier = RecordingNotifier()
    ai_active = _held_ai_session(db_session, "AI Growth", "AAPL")

    # An earlier snapshot anchors the benchmark start; prices bracket the window.
    start = date(2026, 1, 2)
    as_of = date(2026, 1, 5)
    paper_service.record_value_snapshot(
        db_session, session_id=ai_active.id, as_of=start, broker=broker
    )
    db_session.add(BenchmarkPrice(benchmark="SP500", price_date=start, close=100.0))
    db_session.add(BenchmarkPrice(benchmark="SP500", price_date=as_of, close=110.0))
    db_session.commit()

    service.snapshot_all_sessions(
        db_session, broker=broker, notifier=notifier, as_of=as_of
    )

    message, _ = notifier.sent[0]
    # The per-session line carries the benchmark comparison (display name + excess).
    assert "vs S&P 500" in message
    assert "excess" in message


def test_snapshot_report_omits_benchmark_when_unavailable(
    db_session: Session,
) -> None:
    broker = StubBroker()
    notifier = RecordingNotifier()
    _held_ai_session(db_session, "AI Growth", "AAPL")

    # No benchmark prices stored -> the comparison suffix is omitted gracefully.
    service.snapshot_all_sessions(
        db_session, broker=broker, notifier=notifier, as_of=date(2026, 1, 5)
    )

    message, title = notifier.sent[0]
    assert title == "Cadence: AI Growth daily P&L"
    assert "vs S&P 500" not in message


# --------------------------------------------------------------------------- #
# Technical-indicator trend gate (v3): candidate hard-filter, holdings context,
# and per-run trend-decision context.
# --------------------------------------------------------------------------- #


def _seed_trend_prompt(db_session: Session) -> None:
    """Seed the trend (v3) rebalance prompt so builds/rebalances gate."""
    db_session.add(
        RebalancePrompt(
            version=TREND_PROMPT_VERSION,
            instructions="v3 trend instructions {max_new_assets}",
            input_template=(
                "v3 {risk_profile} {candidates_json} {holdings_json} "
                "{account_summary_json}"
            ),
        )
    )
    db_session.flush()


def _seed_snapshot(
    db_session: Session,
    ticker: str,
    *,
    gate_pass: bool = True,
    regime_pass: bool = True,
    momentum_pass: bool = True,
    rsi_rollover: bool = False,
) -> None:
    """Attach a technical-indicator snapshot to an existing universe asset."""
    asset = db_session.execute(
        select(Asset).where(Asset.ticker == ticker)
    ).scalar_one()
    db_session.add(
        TechnicalIndicator(
            asset_id=asset.id,
            trading_date=date(2026, 1, 2),
            close=100.0,
            sma_50=95.0,
            sma_200=90.0,
            close_sma200=1.11,
            sma50_sma200=1.05,
            sma200_slope=0.5,
            rsi_14=60.0,
            roc_120=0.2,
            macd_hist=0.3,
            gate_pass=gate_pass,
            regime_pass=regime_pass,
            momentum_pass=momentum_pass,
            obv_rising=True,
            rev_macd_hist_rollover=False,
            rev_rsi_rollover=rsi_rollover,
            rev_return_decel=False,
            rev_obv_price_divergence=False,
            rev_sma200_slope_flattening=False,
        )
    )
    db_session.flush()


def test_run_build_event_gates_candidates_and_records_trend_context(
    db_session: Session,
) -> None:
    # A v3-active build hard-filters the candidate set: only assets whose stored
    # snapshot passes the gate reach the AI; failing / snapshot-less assets are
    # dropped and recorded in the per-run trend context.
    provider = _seed_universe(db_session, "AAPL", "MSFT", "GOOG")
    _seed_trend_prompt(db_session)
    _seed_snapshot(db_session, "AAPL", gate_pass=True)
    _seed_snapshot(db_session, "MSFT", gate_pass=False, regime_pass=False)
    # GOOG intentionally has no snapshot -> dropped as "no snapshot".

    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL"))
    event = service.create_build_event(
        db_session, _params(use_technical_indicators=True)
    )
    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    # Only the gate-passing AAPL is shown to the AI, and it carries indicators.
    assert agent.build_calls
    candidates = agent.build_calls[0]["candidates"]
    assert {c["ticker"] for c in candidates} == {"AAPL"}
    assert "indicators" in candidates[0]

    refreshed = service.get_event(db_session, event.id)
    ctx = refreshed.trend_context
    assert ctx is not None
    dropped = {d["ticker"]: d["reason"] for d in ctx["dropped_candidates"]}
    assert set(dropped) == {"MSFT", "GOOG"}
    assert dropped["GOOG"] == "no snapshot"
    assert "regime" in dropped["MSFT"]
    assert {c["ticker"] for c in ctx["candidates"]} == {"AAPL"}
    assert ctx["holdings"] == []  # builds record no holdings


def test_run_build_event_pre_v3_records_no_trend_context(
    db_session: Session,
) -> None:
    # The conftest seeds only v1, so a build performs no gating: every asset is a
    # candidate (no indicator payload) and no trend context is recorded.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    assert agent.build_calls
    candidates = agent.build_calls[0]["candidates"]
    assert {c["ticker"] for c in candidates} == {"AAPL", "MSFT"}
    assert all("indicators" not in c for c in candidates)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.trend_context is None


def _seed_gated_session(
    db_session: Session, broker: StubBroker, provider: FakeMarketDataProvider
) -> object:
    """Build a v3-gated 3-holding session (AAPL, MSFT, NVDA all gate-passing)."""
    _seed_universe(db_session, "AAPL", "MSFT", "NVDA")
    _seed_trend_prompt(db_session)
    for ticker in ("AAPL", "MSFT", "NVDA"):
        _seed_snapshot(db_session, ticker, gate_pass=True)
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    build_event = service.create_build_event(
        db_session,
        _params(
            allocated_capital=50_000.0,
            daily_rebalancing=True,
            use_technical_indicators=True,
        ),
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    return service.get_event(db_session, build_event.id).session_id


def test_run_rebalance_event_gates_candidates_and_annotates_holdings(
    db_session: Session,
) -> None:
    provider = _provider()
    broker = StubBroker()
    session_id = _seed_gated_session(db_session, broker, provider)
    assert (
        paper_service.get_session(db_session, session_id).rebalance_prompt_version
        == TREND_PROMPT_VERSION
    )

    # Two extra candidates enter the universe post-build: one fails the gate, one
    # has no snapshot. Both must be dropped from the AI's candidate set.
    assets_service.add_asset(db_session, "TSLA", provider, broker)
    assets_service.add_asset(db_session, "AMZN", provider, broker)
    _seed_snapshot(db_session, "TSLA", gate_pass=False, momentum_pass=False)
    # AMZN has no snapshot.

    rebalance = _noop_rebalance()
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    call = rebalance.rebalance_calls[0]
    # TSLA (fail) and AMZN (no snapshot) are hidden; only gate-passers remain.
    assert {c["ticker"] for c in call["candidates"]} == {"AAPL", "MSFT", "NVDA"}
    # Every holding carries its indicator + reversal payload (no hard exit).
    assert call["holdings"]
    for holding in call["holdings"]:
        assert holding["indicators"] is not None
        assert holding["reversal_flags"] is not None

    refreshed = service.get_event(db_session, rb_event.id)
    ctx = refreshed.trend_context
    assert ctx is not None
    dropped = {d["ticker"]: d["reason"] for d in ctx["dropped_candidates"]}
    assert set(dropped) == {"TSLA", "AMZN"}
    assert dropped["AMZN"] == "no snapshot"
    assert {h["ticker"] for h in ctx["holdings"]} == {"AAPL", "MSFT", "NVDA"}


def test_run_rebalance_event_persists_trend_context_on_failure(
    db_session: Session,
) -> None:
    provider = _provider()
    broker = StubBroker()
    session_id = _seed_gated_session(db_session, broker, provider)

    # The agent raises mid-run, after the trend context has been assembled.
    rebalance = FakeAIPortfolioAgent(rebalance_error=RuntimeError("rebalance boom"))
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.FAILED.value
    # The context captured before the failure is still persisted for review.
    assert refreshed.trend_context is not None
    assert {h["ticker"] for h in refreshed.trend_context["holdings"]} == {
        "AAPL",
        "MSFT",
        "NVDA",
    }


def test_run_rebalance_event_pre_v3_records_no_trend_context(
    db_session: Session,
) -> None:
    # A session frozen to the conftest v1 prompt performs no gating: holdings carry
    # no indicator payload and the event records no trend context.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)

    rebalance = _noop_rebalance()
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    for holding in rebalance.rebalance_calls[0]["holdings"]:
        assert "indicators" not in holding
        assert "reversal_flags" not in holding

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.trend_context is None


# --------------------------------------------------------------------------- #
# Technical-indicator opt-in: the trend strategy is off by default and disabled
# for both build and rebalance unless the session opted in at build time.
# --------------------------------------------------------------------------- #


def test_run_build_event_opted_out_ignores_trend_gate(
    db_session: Session,
) -> None:
    # Even with the trend prompt active and gating snapshots stored, a build that
    # did not opt in (the default) applies no gate: every in-scope asset reaches the
    # AI without indicator annotations, and no trend context is recorded.
    provider = _seed_universe(db_session, "AAPL", "MSFT", "GOOG")
    _seed_trend_prompt(db_session)
    _seed_snapshot(db_session, "AAPL", gate_pass=True)
    _seed_snapshot(db_session, "MSFT", gate_pass=False, regime_pass=False)
    # GOOG has no snapshot; it would be dropped as "no snapshot" if gated.

    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL"))
    # No use_technical_indicators -> defaults to opted out.
    event = service.create_build_event(db_session, _params())
    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    assert agent.build_calls
    candidates = agent.build_calls[0]["candidates"]
    assert {c["ticker"] for c in candidates} == {"AAPL", "MSFT", "GOOG"}
    assert all("indicators" not in c for c in candidates)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.trend_context is None
    # The opt-out is frozen on the session.
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.use_technical_indicators is False


def test_run_rebalance_event_opted_out_ignores_trend_gate(
    db_session: Session,
) -> None:
    # A session that opted out but is frozen to the trend prompt still performs no
    # gating on rebalance: extra failing/snapshot-less candidates are NOT dropped,
    # holdings carry no indicator/reversal context, and no trend context is recorded.
    provider = _provider()
    broker = StubBroker()
    _seed_universe(db_session, "AAPL", "MSFT", "NVDA")
    _seed_trend_prompt(db_session)
    for ticker in ("AAPL", "MSFT", "NVDA"):
        _seed_snapshot(db_session, ticker, gate_pass=True)

    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    build_event = service.create_build_event(
        db_session,
        _params(allocated_capital=50_000.0, daily_rebalancing=True),
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id

    # The session froze to the trend prompt version but opted out.
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.rebalance_prompt_version == TREND_PROMPT_VERSION
    assert session_row.use_technical_indicators is False

    # A gate-failing candidate enters the universe post-build; opted out, it must
    # NOT be dropped from the AI's candidate set.
    assets_service.add_asset(db_session, "TSLA", provider, broker)
    _seed_snapshot(db_session, "TSLA", gate_pass=False, momentum_pass=False)

    rebalance = _noop_rebalance()
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    assert rebalance.rebalance_calls
    call = rebalance.rebalance_calls[0]
    assert "TSLA" in {c["ticker"] for c in call["candidates"]}
    for candidate in call["candidates"]:
        assert "indicators" not in candidate
    for holding in call["holdings"]:
        assert "indicators" not in holding
        assert "reversal_flags" not in holding

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.trend_context is None


def test_run_build_event_persists_opt_in_flag(db_session: Session) -> None:
    # The opt-in is persisted on the session (frozen at build) and exposed on the
    # read schema; a legacy/default build persists it as False.
    from cadence.api.schemas import PaperTradingSessionRead

    provider = _seed_universe(db_session, "AAPL", "MSFT", "NVDA")
    _seed_trend_prompt(db_session)
    for ticker in ("AAPL", "MSFT", "NVDA"):
        _seed_snapshot(db_session, ticker, gate_pass=True)

    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT", "NVDA"))
    event = service.create_build_event(
        db_session, _params(use_technical_indicators=True)
    )
    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    session_row = paper_service.get_session(
        db_session, service.get_event(db_session, event.id).session_id
    )
    assert session_row.use_technical_indicators is True
    read = PaperTradingSessionRead.model_validate(session_row)
    assert read.use_technical_indicators is True


# --------------------------------------------------------------------------- #
# Stop-loss: build persistence, scan/evaluation/execution, quarantine, notify
# --------------------------------------------------------------------------- #


def _build_stop_loss_session(
    db_session: Session,
    provider: FakeMarketDataProvider,
    *tickers: str,
    pct: float = 0.15,
    broker: _StopLossBroker | None = None,
) -> tuple[object, _StopLossBroker]:
    """Build an opted-in stop-loss session holding ``tickers`` (universe pre-seeded).

    Returns the session id and the broker used, which must be reused for the scan so
    the stub broker's in-memory positions carry over from the build's buys.
    """
    broker = broker or _StopLossBroker()
    agent = FakeAIPortfolioAgent(build_result=_build_result(*tickers))
    event = service.create_build_event(
        db_session, _params(stop_loss_enabled=True, stop_loss_pct=pct)
    )
    service.run_build_event(db_session, event.id, agent, broker, provider)
    return service.get_event(db_session, event.id).session_id, broker


def _stop_loss_session(
    db_session: Session, *tickers: str, pct: float = 0.15
) -> tuple[object, _StopLossBroker]:
    """Seed ``tickers`` into the universe and build one opted-in stop-loss session."""
    provider = _seed_universe(db_session, *tickers)
    return _build_stop_loss_session(db_session, provider, *tickers, pct=pct)


def _below_trigger(entry: object, pct: float) -> float:
    """A quote price just under the stop-loss trigger for ``entry``."""
    return entry.avg_cost * (1 - pct) - 1.0


def _ledger_by_ticker(db_session: Session, session_id: object) -> dict[str, object]:
    return {p.ticker: p for p in paper_service.list_open_positions(db_session, session_id)}


def test_run_build_event_persists_stop_loss_opt_in(db_session: Session) -> None:
    # The stop-loss opt-in and its threshold are frozen onto the session at build.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(
        db_session, _params(stop_loss_enabled=True, stop_loss_pct=0.2)
    )
    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    session_row = paper_service.get_session(
        db_session, service.get_event(db_session, event.id).session_id
    )
    assert session_row.stop_loss_enabled is True
    assert session_row.stop_loss_pct == 0.2


def test_run_build_event_default_disables_stop_loss(db_session: Session) -> None:
    # A default build leaves the stop-loss off and its threshold null.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())
    service.run_build_event(db_session, event.id, agent, StubBroker(), provider)

    session_row = paper_service.get_session(
        db_session, service.get_event(db_session, event.id).session_id
    )
    assert session_row.stop_loss_enabled is False
    assert session_row.stop_loss_pct is None


def test_scan_stop_losses_triggers_below_threshold_only(db_session: Session) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", "MSFT", pct=0.15)
    ledger = _ledger_by_ticker(db_session, session_id)
    broker.set_overrides(
        {
            # AAPL breaches its trigger; MSFT stays at cost (comfortably above).
            "AAPL": _below_trigger(ledger["AAPL"], 0.15),
            "MSFT": ledger["MSFT"].avg_cost,
        }
    )

    outcomes = service.scan_stop_losses(db_session, broker=broker)

    assert {o.ticker for o in outcomes} == {"AAPL"}
    remaining = set(_ledger_by_ticker(db_session, session_id))
    assert "AAPL" not in remaining
    assert "MSFT" in remaining


def test_scan_stop_losses_ignores_non_opted_in_sessions(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = _StopLossBroker()
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    event = service.create_build_event(db_session, _params())  # stop-loss OFF
    service.run_build_event(db_session, event.id, agent, broker, provider)
    session_id = service.get_event(db_session, event.id).session_id

    ledger = _ledger_by_ticker(db_session, session_id)
    broker.set_overrides(
        {t: p.avg_cost * 0.1 for t, p in ledger.items()}  # far below trigger
    )

    outcomes = service.scan_stop_losses(db_session, broker=broker)

    assert outcomes == []  # opted-out session is never scanned
    assert set(_ledger_by_ticker(db_session, session_id)) == {"AAPL", "MSFT"}


def test_scan_stop_losses_records_trade_run_closed_and_fee(
    db_session: Session,
) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", pct=0.15)
    fees_before = paper_service.get_session(db_session, session_id).total_fees
    aapl = _ledger_by_ticker(db_session, session_id)["AAPL"]
    broker.set_overrides({"AAPL": _below_trigger(aapl, 0.15)})

    outcomes = service.scan_stop_losses(db_session, broker=broker)
    assert len(outcomes) == 1

    trades = paper_service.get_session_trades(db_session, session_id, limit=100)
    stop_trade = next(t for t in trades if t.signal_type == STOP_LOSS_SIGNAL_TYPE)
    assert stop_trade.side == OrderSide.SELL.value
    assert stop_trade.ai_portfolio_event_id is None

    runs = paper_service.get_session_runs(db_session, session_id, limit=100)
    assert any(r.run_trigger == STOP_LOSS_RUN_TRIGGER for r in runs)

    closed = paper_service.get_closed_positions(db_session, session_id, limit=100)
    assert any(c.ticker == "AAPL" for c in closed)

    fees_after = paper_service.get_session(db_session, session_id).total_fees
    assert fees_after > fees_before  # the flat transaction cost was charged


def _seed_and_build_mixed_stop_loss(
    db_session: Session, pct: float = 0.15
) -> tuple[object, _StopLossBroker]:
    """Build an opted-in session holding one equity (AAPL) and one crypto (BTC-USD)."""
    _seed_mixed_universe(db_session)
    broker = _StopLossBroker()
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "BTC-USD"))
    event = service.create_build_event(
        db_session, _params(stop_loss_enabled=True, stop_loss_pct=pct)
    )
    service.run_build_event(db_session, event.id, agent, broker, _provider())
    return service.get_event(db_session, event.id).session_id, broker


def test_scan_stop_losses_defers_equity_when_market_closed(
    db_session: Session,
) -> None:
    session_id, broker = _seed_and_build_mixed_stop_loss(db_session, pct=0.15)
    ledger = _ledger_by_ticker(db_session, session_id)
    broker.set_overrides(
        {
            "AAPL": _below_trigger(ledger["AAPL"], 0.15),
            "BTC-USD": _below_trigger(ledger["BTC-USD"], 0.15),
        }
    )
    broker.set_market_open(False)

    outcomes = service.scan_stop_losses(db_session, broker=broker)

    # Equity sell is deferred while the market is closed; crypto stops out anytime.
    assert {o.ticker for o in outcomes} == {"BTC-USD"}
    remaining = set(_ledger_by_ticker(db_session, session_id))
    assert "AAPL" in remaining
    assert "BTC-USD" not in remaining


def test_scan_stop_losses_skips_missing_quote(db_session: Session) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", pct=0.15)
    # A price-less quote leaves the position untouched for the next scan.
    broker.set_overrides({"AAPL": None})

    outcomes = service.scan_stop_losses(db_session, broker=broker)

    assert outcomes == []
    assert "AAPL" in _ledger_by_ticker(db_session, session_id)


def test_scan_stop_losses_isolates_session_failures(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    # Both sessions share one broker so its in-memory positions cover both builds.
    broker = _StopLossBroker()
    s1, _ = _build_stop_loss_session(db_session, provider, "AAPL", pct=0.15, broker=broker)
    s2, _ = _build_stop_loss_session(db_session, provider, "MSFT", pct=0.15, broker=broker)

    original = service._scan_session_stop_losses

    def flaky(session, session_row, **kwargs):  # type: ignore[no-untyped-def]
        if session_row.id == s1:
            raise RuntimeError("boom")
        return original(session, session_row, **kwargs)

    monkeypatch.setattr(service, "_scan_session_stop_losses", flaky)

    ledger1 = _ledger_by_ticker(db_session, s1)
    ledger2 = _ledger_by_ticker(db_session, s2)
    broker.set_overrides(
        {
            "AAPL": _below_trigger(ledger1["AAPL"], 0.15),
            "MSFT": _below_trigger(ledger2["MSFT"], 0.15),
        }
    )

    outcomes = service.scan_stop_losses(db_session, broker=broker)

    # The failing session is skipped; the healthy one still stops out.
    assert {o.ticker for o in outcomes} == {"MSFT"}
    assert "MSFT" not in _ledger_by_ticker(db_session, s2)


def test_scan_stop_losses_quarantines_stopped_ticker(db_session: Session) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", pct=0.15)
    aapl = _ledger_by_ticker(db_session, session_id)["AAPL"]
    broker.set_overrides({"AAPL": _below_trigger(aapl, 0.15)})

    reference = datetime.now(UTC)
    service.scan_stop_losses(db_session, broker=broker)

    quarantined = paper_service.list_active_quarantined_tickers(db_session, session_id)
    assert "AAPL" in quarantined

    rows = list(
        db_session.execute(
            select(StopLossQuarantine).where(
                StopLossQuarantine.session_id == session_id
            )
        ).scalars()
    )
    assert len(rows) == 1
    expected = service._trading_days_ahead(
        reference, settings.STOP_LOSS_COOLDOWN_TRADING_DAYS
    )
    assert rows[0].excluded_until.date() == expected.date()


def test_rebalance_excludes_quarantined_not_held_ticker(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT", "NVDA", "TSLA")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)  # holds AAPL/MSFT/NVDA
    paper_service.add_stop_loss_quarantine(
        db_session,
        session_id=session_id,
        ticker="TSLA",
        excluded_until=datetime.now(UTC) + timedelta(days=5),
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    candidates = {c["ticker"] for c in rebalance.rebalance_calls[0]["candidates"]}
    assert "TSLA" not in candidates  # freshly quarantined, not held → excluded
    assert {"AAPL", "MSFT", "NVDA"} <= candidates


def test_rebalance_includes_expired_quarantine_ticker(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT", "NVDA", "TSLA")
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker, provider)
    paper_service.add_stop_loss_quarantine(
        db_session,
        session_id=session_id,
        ticker="TSLA",
        excluded_until=datetime.now(UTC) - timedelta(days=1),  # already expired
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker, provider)

    candidates = {c["ticker"] for c in rebalance.rebalance_calls[0]["candidates"]}
    assert "TSLA" in candidates  # expired quarantine no longer excludes


def test_scan_stop_losses_notifies_on_stop_out(db_session: Session) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", pct=0.15)
    aapl = _ledger_by_ticker(db_session, session_id)["AAPL"]
    broker.set_overrides({"AAPL": _below_trigger(aapl, 0.15)})
    notifier = RecordingNotifier()

    service.scan_stop_losses(db_session, broker=broker, notifier=notifier)

    assert notifier.sent  # a best-effort push was sent for the stop-out


def test_scan_stop_losses_records_sale_when_notify_fails(db_session: Session) -> None:
    session_id, broker = _stop_loss_session(db_session, "AAPL", pct=0.15)
    aapl = _ledger_by_ticker(db_session, session_id)["AAPL"]
    broker.set_overrides({"AAPL": _below_trigger(aapl, 0.15)})
    notifier = RecordingNotifier(raises=True)  # notifier blows up

    outcomes = service.scan_stop_losses(db_session, broker=broker, notifier=notifier)

    # The sale is still recorded despite the notifier failure.
    assert len(outcomes) == 1
    assert "AAPL" not in _ledger_by_ticker(db_session, session_id)


# --------------------------------------------------------------------------- #
# Build-order readiness gate (defer daily rebalance until build orders fill)
# --------------------------------------------------------------------------- #


class _OrderBroker:
    """Broker double whose ``get_order`` returns pre-seeded orders by id.

    Only ``get_order`` is exercised by build-order reconciliation. An unseeded id
    resolves to ``None`` (unknown order — reconciliation leaves the trade as-is).
    """

    def __init__(self, orders: dict[str, object] | None = None) -> None:
        self._orders = orders or {}

    def get_order(self, order_id: str) -> object | None:
        return self._orders.get(order_id)


def _session_with_build_trades(
    db: Session,
    trades: list[tuple[str | None, OrderStatus]],
    *,
    with_build_event: bool = True,
) -> object:
    """Create an AI session plus a build event and its trades at given statuses.

    ``trades`` is a list of ``(order_id, order_status)``. When ``with_build_event``
    is False no build event is linked (session_metadata carries no build_event_id).
    """
    portfolio = portfolios_service.create_portfolio(db, name="P", stocks=["AAPL"])
    session_row = paper_service.create_session(
        db,
        portfolio_id=portfolio.id,
        strategy_key="ai_buy_hold",
        rebalance_prompt_version=1,
        benchmark=Benchmark.SP500,
        schedule_mode=ScheduleMode.DAILY_REBALANCING,
    )
    if with_build_event:
        event = AIPortfolioEvent(
            event_type=EventType.BUILD.value,
            status=EventStatus.SUCCEEDED.value,
            session_id=session_row.id,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        session_row.session_metadata = {"build_event_id": str(event.id)}
        db.commit()
        for i, (order_id, status) in enumerate(trades):
            paper_service.record_trade(
                db,
                session_id=session_row.id,
                ticker=f"T{i}",
                side=OrderSide.BUY,
                quantity=1,
                price=10.0,
                signal_type="entry",
                order_id=order_id,
                order_status=status,
                ai_portfolio_event_id=event.id,
            )
    return session_row


def test_build_orders_settled_all_filled_is_ready(db_session: Session) -> None:
    session_row = _session_with_build_trades(
        db_session, [("o1", OrderStatus.FILLED), ("o2", OrderStatus.FILLED)]
    )
    assert service.build_orders_settled(db_session, _OrderBroker(), session_row)


def test_build_orders_settled_pending_order_defers(db_session: Session) -> None:
    session_row = _session_with_build_trades(
        db_session, [("o1", OrderStatus.FILLED), ("o2", OrderStatus.SUBMITTED)]
    )
    # The broker still reports o2 as unknown/unsettled, so it stays non-terminal.
    assert not service.build_orders_settled(db_session, _OrderBroker(), session_row)


def test_build_orders_settled_no_build_event_is_ready(db_session: Session) -> None:
    session_row = _session_with_build_trades(db_session, [], with_build_event=False)
    assert service.build_orders_settled(db_session, _OrderBroker(), session_row)


def test_build_orders_settled_terminal_non_filled_does_not_strand(
    db_session: Session,
) -> None:
    session_row = _session_with_build_trades(
        db_session, [("o1", OrderStatus.FILLED), ("o2", OrderStatus.CANCELLED)]
    )
    # A cancelled/rejected order will never fill, so it must not defer forever.
    assert service.build_orders_settled(db_session, _OrderBroker(), session_row)


def test_build_orders_settled_no_broker_order_id_is_ready(db_session: Session) -> None:
    # A build trade with no broker order id has nothing to reconcile/wait on.
    session_row = _session_with_build_trades(db_session, [(None, OrderStatus.SUBMITTED)])
    assert service.build_orders_settled(db_session, _OrderBroker(), session_row)


def test_build_orders_settled_fails_safe_when_reconcile_raises(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_row = _session_with_build_trades(
        db_session, [("o1", OrderStatus.SUBMITTED)]
    )

    def boom(*_args: object, **_kw: object) -> object:
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(paper_service, "reconcile_session_orders", boom)
    # Cannot confirm fills -> defer rather than rebalance on unverified state.
    assert not service.build_orders_settled(db_session, _OrderBroker(), session_row)
