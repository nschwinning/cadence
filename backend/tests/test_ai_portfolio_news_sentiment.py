"""Tests for the news-sentiment rebalance integration.

The helper-level tests exercise the gate-controlled attachment onto candidate /
holding dicts in isolation (no DB, no agent, no network), mirroring
``test_ai_portfolio_price_ml.py``. The flow-level tests drive a real build +
rebalance and assert the end-to-end gate: a session opted into news sentiment and
frozen on the sentiment-aware prompt version attaches the block to the agent's
candidates and holdings; an opted-out session, or one frozen on an older prompt
version, attaches nothing; a resolved tone surfaces as ``available`` while an asset
with no usable news is explicitly marked ``unavailable`` (never fabricated); and a
rebalance still proceeds when the sentiment service is unconfigured/down.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent
from tests.test_ai_portfolio_service import (  # reuse the flow harness
    _build_result,
    _flat_rebalance_result,
    _params,
    _seed_universe,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio._helpers import _build_holdings, _candidates_from_universe
from cadence.ai_portfolio.constants import (
    NEWS_SENTIMENT_PROMPT_VERSION,
    PRICE_ML_PROMPT_VERSION,
    EventStatus,
)
from cadence.ai_portfolio.flows import rebalance as rebalance_flow
from cadence.ai_portfolio.models import RebalancePrompt
from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.models import SessionPosition

# --------------------------------------------------------------------------- #
# Version constant
# --------------------------------------------------------------------------- #


def test_news_sentiment_prompt_version_is_after_price_ml() -> None:
    assert NEWS_SENTIMENT_PROMPT_VERSION > PRICE_ML_PROMPT_VERSION
    assert NEWS_SENTIMENT_PROMPT_VERSION == 6


# --------------------------------------------------------------------------- #
# Build params round-trip
# --------------------------------------------------------------------------- #


def test_ai_build_params_news_sentiment_round_trip() -> None:
    # The news-sentiment opt-in must survive to_payload -> from_payload, default off.
    from cadence.ai_portfolio.service import AIBuildParams

    assert AIBuildParams(allocated_capital=1.0).use_news_sentiment is False
    params = AIBuildParams(allocated_capital=50_000.0, use_news_sentiment=True)
    restored = AIBuildParams.from_payload(params.to_payload())
    assert restored == params
    assert restored.use_news_sentiment is True
    # A legacy payload with no key degrades to opted out.
    legacy = AIBuildParams.from_payload({"allocated_capital": 1.0})
    assert legacy.use_news_sentiment is False


# --------------------------------------------------------------------------- #
# Candidate / holding attach helpers (no DB)
# --------------------------------------------------------------------------- #


def _asset(ticker: str) -> Asset:
    return Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        is_eligible=True,
    )


def _ledger(*tickers: str) -> list[SessionPosition]:
    return [SessionPosition(ticker=t, quantity=10.0, avg_cost=50.0) for t in tickers]


def test_candidates_attach_news_sentiment_when_map_given() -> None:
    assets = [_asset("AAPL"), _asset("NONEWS")]
    candidates, _ = _candidates_from_universe(
        assets,
        {},
        apply_gate=False,
        news_sentiment_by_ticker={
            "AAPL": {"status": "available", "tone": "positive", "article_count": 4}
        },
    )
    by_ticker = {c["ticker"]: c for c in candidates}
    assert by_ticker["AAPL"]["news_sentiment"]["status"] == "available"
    assert by_ticker["AAPL"]["news_sentiment"]["tone"] == "positive"
    # A ticker missing from the map -> explicit unavailable marker, not fabricated.
    assert by_ticker["NONEWS"]["news_sentiment"] == {"status": "unavailable"}


def test_candidates_omit_news_sentiment_when_map_none() -> None:
    candidates, _ = _candidates_from_universe(
        [_asset("AAPL")], {}, apply_gate=False, news_sentiment_by_ticker=None
    )
    assert all("news_sentiment" not in c for c in candidates)


def test_holdings_attach_news_sentiment_when_map_given() -> None:
    broker = StubBroker()
    holdings = _build_holdings(
        _ledger("AAPL", "MSFT"),
        broker,
        {},
        news_sentiment_by_ticker={
            "AAPL": {"status": "available", "tone": "negative", "article_count": 2}
        },
    )
    by_ticker = {h["ticker"]: h for h in holdings}
    assert by_ticker["AAPL"]["news_sentiment"] == {
        "status": "available",
        "tone": "negative",
        "article_count": 2,
    }
    # A held ticker absent from the map falls back to the unavailable marker.
    assert by_ticker["MSFT"]["news_sentiment"] == {"status": "unavailable"}


def test_holdings_omit_news_sentiment_when_map_none() -> None:
    broker = StubBroker()
    holdings = _build_holdings(_ledger("AAPL"), broker, {})
    assert all("news_sentiment" not in h for h in holdings)


# --------------------------------------------------------------------------- #
# Flow-level gate (build + rebalance)
# --------------------------------------------------------------------------- #


def _seed_v6_prompt(db_session: Session) -> None:
    """Make the sentiment-aware version (6) the active rebalance prompt."""
    db_session.add(
        RebalancePrompt(
            version=NEWS_SENTIMENT_PROMPT_VERSION,
            instructions="v6 instructions {max_new_assets}",
            input_template="v6 input {risk_profile} {candidates_json}",
        )
    )
    db_session.flush()


def _build_opted_in_session(
    db_session: Session,
    broker: StubBroker,
    provider: object,
    *,
    use_news_sentiment: bool,
    seed_v6: bool,
) -> object:
    """Build a session (optionally opted into news sentiment and frozen on v6) and run
    its opening allocation so it holds AAPL + MSFT."""
    if seed_v6:
        _seed_v6_prompt(db_session)
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db_session,
        _params(allocated_capital=50_000.0, use_news_sentiment=use_news_sentiment),
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id
    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)
    return session_id


def _patch_resolver(
    monkeypatch: Any, mapping: dict[str, dict[str, Any]]
) -> None:
    """Stand in for the sentiment resolver so a flow run surfaces a canned tone map
    (the real service needs an out-of-process sidecar). Tickers absent from the map
    fall back to the unavailable marker inside the attach helpers."""

    def _fake(tickers: Any, **_kw: Any) -> dict[str, dict[str, Any]]:
        return {t: mapping[t] for t in tickers if t in mapping}

    monkeypatch.setattr(
        rebalance_flow.news_sentiment_service,
        "resolve_sentiment_annotations",
        _fake,
    )


def test_rebalance_attaches_news_sentiment_when_opted_in(
    db_session: Session, monkeypatch: Any
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_news_sentiment=True, seed_v6=True
    )
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.use_news_sentiment is True
    assert session_row.rebalance_prompt_version == NEWS_SENTIMENT_PROMPT_VERSION

    # AAPL resolves to an available tone; MSFT has no usable news -> unavailable.
    _patch_resolver(
        monkeypatch,
        {
            "AAPL": {
                "status": "available",
                "tone": "positive",
                "score": 0.42,
                "article_count": 5,
            }
        },
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    assert service.get_event(db_session, rb.id).status == EventStatus.SUCCEEDED.value
    call = rebalance.rebalance_calls[0]
    cands = {c["ticker"]: c for c in call["candidates"]}
    assert cands["AAPL"]["news_sentiment"]["status"] == "available"
    assert cands["AAPL"]["news_sentiment"]["tone"] == "positive"
    assert cands["MSFT"]["news_sentiment"] == {"status": "unavailable"}
    holds = {h["ticker"]: h for h in call["holdings"]}
    assert holds["AAPL"]["news_sentiment"]["status"] == "available"
    assert holds["MSFT"]["news_sentiment"] == {"status": "unavailable"}


def test_rebalance_omits_news_sentiment_when_opted_out(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Opted out (default) but v6 is still active: the gate must stay off.
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_news_sentiment=False, seed_v6=True
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    call = rebalance.rebalance_calls[0]
    assert all("news_sentiment" not in c for c in call["candidates"])
    assert all("news_sentiment" not in h for h in call["holdings"])


def test_rebalance_omits_news_sentiment_when_frozen_version_too_old(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Opted in, but no v6 prompt: the session freezes conftest's v1 (< 6), so the
    # gate stays off even though the flag is on.
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_news_sentiment=True, seed_v6=False
    )
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.use_news_sentiment is True
    assert session_row.rebalance_prompt_version < NEWS_SENTIMENT_PROMPT_VERSION

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    call = rebalance.rebalance_calls[0]
    assert all("news_sentiment" not in c for c in call["candidates"])
    assert all("news_sentiment" not in h for h in call["holdings"])


def test_initial_allocation_inherits_news_sentiment(
    db_session: Session, monkeypatch: Any
) -> None:
    # The opening allocation now runs as the session's first rebalance, so it
    # inherits the news-sentiment block with no extra wiring.
    _seed_v6_prompt(db_session)
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    _patch_resolver(
        monkeypatch,
        {"AAPL": {"status": "available", "tone": "positive", "article_count": 3}},
    )
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, use_news_sentiment=True)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id

    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)

    assert (
        service.get_event(db_session, opening.id).status
        == EventStatus.SUCCEEDED.value
    )
    # The opening allocation is the agent's first rebalance call.
    call = agent.rebalance_calls[0]
    cands = {c["ticker"]: c for c in call["candidates"]}
    assert cands["AAPL"]["news_sentiment"]["status"] == "available"
    assert cands["AAPL"]["news_sentiment"]["tone"] == "positive"
    assert cands["MSFT"]["news_sentiment"] == {"status": "unavailable"}


def test_rebalance_proceeds_when_service_unavailable(db_session: Session) -> None:
    # The degradation contract: an opted-in session whose sentiment service is
    # unconfigured (default empty URL, no scorer injected) still rebalances; every
    # name carries the explicit unavailable marker, never a fabricated tone.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_news_sentiment=True, seed_v6=True
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    assert service.get_event(db_session, rb.id).status == EventStatus.SUCCEEDED.value
    call = rebalance.rebalance_calls[0]
    assert call["candidates"], "expected candidates were assembled"
    assert all(
        c["news_sentiment"] == {"status": "unavailable"} for c in call["candidates"]
    )
    assert all(
        h["news_sentiment"] == {"status": "unavailable"} for h in call["holdings"]
    )
