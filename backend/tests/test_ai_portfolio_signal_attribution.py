"""Signal attribution capture: what a run actually used, recorded for offline learning.

Covers the effective per-run opt-in set on ``run_stats["enabled_signals"]``, the
fundamentals block persisted on ``trend_context`` (mirroring price-ML / news), and the
daily-run learning snapshot surfacing both.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent
from tests.test_ai_portfolio_news_sentiment import (
    _patch_resolver,
    _seed_v6_prompt,
)
from tests.test_ai_portfolio_service import (
    _build_result,
    _flat_rebalance_result,
    _params,
    _seed_universe,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio.constants import NEWS_SENTIMENT_PROMPT_VERSION, EventStatus
from cadence.ai_portfolio.snapshots import _build_run_document
from cadence.api.schemas import AIPortfolioEventRead
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.models import SessionValueSnapshot


def _session(
    db_session: Session,
    broker: StubBroker,
    provider: object,
    *,
    seed_v6: bool,
    **toggles: bool,
) -> Any:
    """Build a session with the given opt-in toggles and run its opening allocation."""
    if seed_v6:
        _seed_v6_prompt(db_session)
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, **toggles)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id
    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)
    return session_id


def _rebalance(
    db_session: Session, session_id: Any, broker: StubBroker, provider: object
) -> tuple[Any, FakeAIPortfolioAgent]:
    agent = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    event = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, event.id, agent, broker, provider)
    return service.get_event(db_session, event.id), agent


def test_run_records_effective_signals_and_fundamentals_block(
    db_session: Session, monkeypatch: Any
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session(
        db_session,
        broker,
        provider,
        seed_v6=True,
        use_fundamentals=True,
        use_news_sentiment=True,
    )
    _patch_resolver(monkeypatch, {})  # every name unavailable

    event, agent = _rebalance(db_session, session_id, broker, provider)

    assert event.status == EventStatus.SUCCEEDED.value
    assert event.run_stats["enabled_signals"] == ["fundamentals", "news_sentiment"]
    # The fundamentals block mirrors exactly what was attached to the prompt.
    call = agent.rebalance_calls[0]
    recorded = event.trend_context["fundamentals"]
    assert {c["ticker"]: c["fundamentals"] for c in recorded["candidates"]} == {
        c["ticker"]: c["fundamentals"] for c in call["candidates"]
    }
    assert {h["ticker"]: h["fundamentals"] for h in recorded["holdings"]} == {
        h["ticker"]: h["fundamentals"] for h in call["holdings"]
    }
    # News stays recorded the way it already was, unavailable markers included.
    assert all(
        c["news_sentiment"] == {"status": "unavailable"}
        for c in event.trend_context["news_sentiment"]["candidates"]
    )


def test_toggle_on_but_prompt_too_old_is_not_listed(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Toggles on, but no v6 prompt: the session freezes conftest's v1, so none of the
    # signals is actually attached and none may be reported as enabled.
    session_id = _session(
        db_session,
        broker,
        provider,
        seed_v6=False,
        use_fundamentals=True,
        use_news_sentiment=True,
        use_price_ml=True,
        use_technical_indicators=True,
    )
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.rebalance_prompt_version < NEWS_SENTIMENT_PROMPT_VERSION

    event, _ = _rebalance(db_session, session_id, broker, provider)

    assert event.run_stats["enabled_signals"] == []
    assert event.trend_context is None or "fundamentals" not in event.trend_context


def test_no_fundamentals_block_when_fundamentals_off(
    db_session: Session, monkeypatch: Any
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session(
        db_session, broker, provider, seed_v6=True, use_news_sentiment=True
    )
    _patch_resolver(monkeypatch, {})

    event, _ = _rebalance(db_session, session_id, broker, provider)

    assert event.run_stats["enabled_signals"] == ["news_sentiment"]
    assert "fundamentals" not in event.trend_context


# Snapshot document ---------------------------------------------------------------
def _value_snapshot() -> SessionValueSnapshot:
    return SessionValueSnapshot(
        snapshot_date=date(2026, 11, 10),
        total_value=10_000.0,
        cash_value=1_000.0,
        positions_value=9_000.0,
        daily_pnl=12.0,
        daily_pnl_pct=0.0012,
        positions=[],
    )


def test_snapshot_document_surfaces_enabled_signals(
    db_session: Session, monkeypatch: Any
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session(
        db_session, broker, provider, seed_v6=True, use_fundamentals=True
    )
    event, _ = _rebalance(db_session, session_id, broker, provider)

    document = _build_run_document(event, [], _value_snapshot())

    assert document["enabled_signals"] == ["fundamentals"]
    assert "fundamentals" in document["run"]["trend_context"]
    assert document["valuation"]["total_value"] == 10_000.0


def test_snapshot_document_without_run_or_key_degrades_to_null(
    db_session: Session,
) -> None:
    no_run = _build_run_document(None, [], _value_snapshot())
    assert no_run["enabled_signals"] is None
    assert no_run["valuation"]["total_value"] == 10_000.0

    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _session(db_session, broker, provider, seed_v6=False)
    event, _ = _rebalance(db_session, session_id, broker, provider)
    event.run_stats = {k: v for k, v in event.run_stats.items() if k != "enabled_signals"}

    older = _build_run_document(event, [], _value_snapshot())
    assert older["enabled_signals"] is None


def test_attribution_stays_backend_only() -> None:
    fields = set(AIPortfolioEventRead.model_fields)
    assert "run_stats" not in fields
    assert "enabled_signals" not in fields
