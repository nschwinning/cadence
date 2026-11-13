"""Tests for the run-context block and per-ticker recent headlines in every rebalance.

Headlines and the run context reach every session — with or without news sentiment,
whatever its frozen prompt version (conftest seeds v1, so these sessions are frozen
on an old version and opted out of sentiment).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent
from tests.test_ai_portfolio_agent import _load_seed_migration, _outcome
from tests.test_ai_portfolio_service import (
    _build_result,
    _flat_rebalance_result,
    _params,
    _seed_universe,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio.agent import _build_rebalance_input
from cadence.ai_portfolio.constants import EventStatus
from cadence.ai_portfolio.flows import rebalance as rebalance_flow
from cadence.broker.stub import StubBroker
from cadence.config import settings
from cadence.news_sentiment import news as news_module
from cadence.news_sentiment.constants import MARKET_TZ
from cadence.news_sentiment.models import NewsItem
from cadence.paper_trading import service as paper_service

_RUN_DATE = date(2026, 11, 13)


# Run context -----------------------------------------------------------------
def _input(**kwargs: Any) -> str:
    return _build_rebalance_input(
        _load_seed_migration()._SEED_INPUT_TEMPLATE,
        holdings=[{"ticker": "AAPL"}],
        account_summary={"cash_available": 1000},
        candidates=[{"ticker": "MSFT"}],
        risk_profile="balanced",
        **kwargs,
    )


def test_run_context_names_the_date_and_guidance() -> None:
    prompt = _input(run_date=_RUN_DATE)
    assert "## Run context" in prompt
    assert "Today is 2026-11-13" in prompt
    for phrase in ("last 7 days", "top_stories", "fiscal years", "recent_headlines"):
        assert phrase in prompt


def test_run_context_comes_last() -> None:
    prompt = _input(
        run_date=_RUN_DATE,
        recent_outcomes=[_outcome("2026-11-12", realized_pnl=1.0, fees_total=0.0, orders_count=1)],
    )
    assert prompt.index("Recent run outcomes") < prompt.index("## Run context")
    assert prompt.rstrip().endswith("publication times.")


def test_no_run_date_leaves_the_input_unchanged() -> None:
    assert "Run context" not in _input()


# Flow --------------------------------------------------------------------------
def _session_holding_aapl_msft(db_session: Session, broker: StubBroker, provider: Any) -> Any:
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(db_session, _params(allocated_capital=50_000.0))
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id
    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)
    return session_id


def _rebalance(db_session: Session, session_id: Any, broker: Any, provider: Any) -> dict[str, Any]:
    agent = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, event.id, agent, broker, provider)
    assert service.get_event(db_session, event.id).status == EventStatus.SUCCEEDED.value
    return agent.rebalance_calls[0]


def _news(ticker: str, headline: str) -> NewsItem:
    return NewsItem(
        ticker=ticker,
        headline=headline,
        summary=None,
        published_at=datetime(2026, 11, 13, 9, tzinfo=MARKET_TZ) - timedelta(hours=1),
        source="Reuters",
    )


def test_headlines_reach_a_session_without_news_sentiment(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session_holding_aapl_msft(db_session, broker, provider)
    assert paper_service.get_session(db_session, session_id).use_news_sentiment is False
    monkeypatch.setattr(rebalance_flow, "_run_date", lambda: _RUN_DATE)
    monkeypatch.setattr(
        news_module.AlpacaNewsSource,
        "fetch_news",
        lambda self, ticker, **kw: [_news(ticker, f"{ticker} news")] if ticker == "AAPL" else [],
    )

    call = _rebalance(db_session, session_id, broker, provider)

    assert call["run_date"] == _RUN_DATE
    holdings = {h["ticker"]: h for h in call["holdings"]}
    candidates = {c["ticker"]: c for c in call["candidates"]}
    assert holdings["AAPL"]["recent_headlines"] == [
        {"headline": "AAPL news", "source": "Reuters", "published_at": "2026-11-13T08:00:00-05:00"}
    ]
    assert candidates["AAPL"]["recent_headlines"][0]["headline"] == "AAPL news"
    assert "recent_headlines" not in holdings["MSFT"]
    assert "news_sentiment" not in holdings["AAPL"]


def test_news_source_failure_does_not_fail_the_run(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session_holding_aapl_msft(db_session, broker, provider)

    def _down(self: Any, ticker: str, **kw: Any) -> list[NewsItem]:
        raise ConnectionError("news down")

    monkeypatch.setattr(news_module.AlpacaNewsSource, "fetch_news", _down)

    call = _rebalance(db_session, session_id, broker, provider)

    assert all("recent_headlines" not in row for row in [*call["holdings"], *call["candidates"]])


def test_headlines_disabled(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session_holding_aapl_msft(db_session, broker, provider)
    fetched: list[str] = []

    def _record(self: Any, ticker: str, **kw: Any) -> list[NewsItem]:
        fetched.append(ticker)
        return [_news(ticker, "x")]

    monkeypatch.setattr(news_module.AlpacaNewsSource, "fetch_news", _record)
    monkeypatch.setattr(settings, "NEWS_HEADLINES_PER_TICKER", 0)

    call = _rebalance(db_session, session_id, broker, provider)

    assert fetched == []
    assert all("recent_headlines" not in row for row in [*call["holdings"], *call["candidates"]])
