"""Service tests for the AI-portfolio build and rebalance flows (stub broker)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent

from cadence.ai_portfolio import service
from cadence.ai_portfolio.agent import (
    AIPortfolioBuildResult,
    AIPortfolioStock,
    AIRebalanceResult,
    ExistingHoldingEvaluation,
    PositionSide,
    RebalanceAction,
)
from cadence.ai_portfolio.constants import EventStatus, EventType
from cadence.ai_portfolio.errors import AIPortfolioValidationError
from cadence.ai_portfolio.service import AIBuildParams
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.constants import ScheduleMode
from cadence.portfolios import service as portfolios_service


class _ClosedBroker(StubBroker):
    def is_market_open(self) -> bool:
        return False


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
        risk_assessment="concentration",
    )


def _params(**kw: object) -> AIBuildParams:
    base: dict[str, object] = {"tickers": ["AAPL", "MSFT"], "allocated_capital": 100_000.0}
    base.update(kw)
    return AIBuildParams(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def test_create_build_event_rejects_too_few_tickers(db_session: Session) -> None:
    with pytest.raises(AIPortfolioValidationError):
        service.create_build_event(db_session, _params(tickers=["AAPL"]))


def test_run_build_event_success_creates_portfolio_and_session(
    db_session: Session,
) -> None:
    agent = FakeAIPortfolioAgent(build_result=_build_result())
    broker = StubBroker()
    event = service.create_build_event(db_session, _params(daily_rebalancing=True))

    service.run_build_event(db_session, event.id, agent, broker)

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert refreshed.event_type == EventType.BUILD.value
    assert refreshed.session_id is not None
    assert refreshed.portfolio_id is not None

    portfolio = portfolios_service.get_portfolio(db_session, refreshed.portfolio_id)
    assert portfolio.source == "ai_managed"
    assert set(portfolio.stocks) == {"AAPL", "MSFT"}

    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.strategy_key == "ai_buy_hold"
    assert session_row.schedule_mode == ScheduleMode.DAILY_REBALANCING.value

    trades = paper_service.get_session_trades(db_session, refreshed.session_id, limit=100)
    assert {t.ticker for t in trades} == {"AAPL", "MSFT"}


def test_run_build_event_manual_schedule_when_not_enrolled(
    db_session: Session,
) -> None:
    agent = FakeAIPortfolioAgent(build_result=_build_result())
    event = service.create_build_event(db_session, _params(daily_rebalancing=False))

    service.run_build_event(db_session, event.id, agent, StubBroker())

    refreshed = service.get_event(db_session, event.id)
    session_row = paper_service.get_session(db_session, refreshed.session_id)
    assert session_row.schedule_mode == ScheduleMode.MANUAL.value


def test_run_build_event_failure_marks_event_failed(db_session: Session) -> None:
    agent = FakeAIPortfolioAgent(build_error=RuntimeError("agent boom"))
    event = service.create_build_event(db_session, _params())

    service.run_build_event(db_session, event.id, agent, StubBroker())

    refreshed = service.get_event(db_session, event.id)
    assert refreshed.status == EventStatus.FAILED.value
    assert "boom" in (refreshed.error or "")


# --------------------------------------------------------------------------- #
# Rebalance
# --------------------------------------------------------------------------- #


def _seed_session(db_session: Session, broker: StubBroker) -> tuple[object, object]:
    agent = FakeAIPortfolioAgent(build_result=_build_result())
    build_event = service.create_build_event(db_session, _params(daily_rebalancing=True))
    service.run_build_event(db_session, build_event.id, agent, broker)
    event = service.get_event(db_session, build_event.id)
    return event.session_id, event.portfolio_id


def test_run_rebalance_event_market_closed_is_skipped(db_session: Session) -> None:
    broker = _ClosedBroker()
    session_id, _ = _seed_session(db_session, broker)

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="x", existing_holdings=[], portfolio_health="healthy"
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SKIPPED.value
    # Agent must not have been consulted while the market was closed.
    assert rebalance.rebalance_calls == []

    runs = paper_service.get_session_runs(db_session, session_id, limit=100)
    assert any(
        r.details and r.details[0].get("skipped") for r in runs
    )


def test_run_rebalance_event_hold_succeeds(db_session: Session) -> None:
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker)

    rebalance = FakeAIPortfolioAgent(
        rebalance_result=AIRebalanceResult(
            evaluation_summary="steady",
            existing_holdings=[
                ExistingHoldingEvaluation(
                    ticker="AAPL",
                    action=RebalanceAction.HOLD,
                    reasoning="keep",
                    confidence=0.9,
                ),
                ExistingHoldingEvaluation(
                    ticker="MSFT",
                    action=RebalanceAction.HOLD,
                    reasoning="keep",
                    confidence=0.9,
                ),
            ],
            portfolio_health="healthy",
        )
    )
    rb_event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb_event.id, rebalance, broker)

    refreshed = service.get_event(db_session, rb_event.id)
    assert refreshed.status == EventStatus.SUCCEEDED.value
    assert rebalance.rebalance_calls  # agent consulted while market open


def test_get_inflight_rebalance_event(db_session: Session) -> None:
    broker = StubBroker()
    session_id, _ = _seed_session(db_session, broker)

    assert service.get_inflight_rebalance_event(db_session, session_id) is None
    rb_event = service.create_rebalance_event(db_session, session_id)
    inflight = service.get_inflight_rebalance_event(db_session, session_id)
    assert inflight is not None
    assert inflight.id == rb_event.id
