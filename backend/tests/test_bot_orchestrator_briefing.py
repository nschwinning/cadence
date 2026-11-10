"""Unit tests for the orchestrator decision briefing."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.bot_orchestrator import briefing
from cadence.bot_orchestrator import service as orchestrator_service
from cadence.paper_trading.models import BenchmarkPrice
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin
from cadence.technical_indicators.models import TechnicalIndicator

_NOW = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)


def _asset(db: Session, ticker: str, sector: str | None = "technology") -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector=sector,
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db.add(asset)
    db.flush()
    return asset


def _indicator(
    db: Session,
    asset: Asset,
    *,
    gate: bool,
    regime: bool,
    rsi: float,
    dist_high: float = -0.05,
) -> TechnicalIndicator:
    row = TechnicalIndicator(
        asset_id=asset.id,
        trading_date=date(2026, 11, 9),
        close=100.0,
        rsi_14=rsi,
        roc_120=0.1,
        dist_high_52w=dist_high,
        hvol_20=0.2,
        gate_pass=gate,
        regime_pass=regime,
        momentum_pass=gate,
        obv_rising=False,
        rev_macd_hist_rollover=False,
        rev_rsi_rollover=False,
        rev_return_decel=False,
        rev_obv_price_divergence=False,
        rev_sma200_slope_flattening=False,
    )
    db.add(row)
    db.flush()
    return row


def _sentiment(
    notes: Mapping[str, Mapping[str, Any]],
) -> briefing.SentimentResolver:
    def resolve(tickers: Sequence[str]) -> Mapping[str, Mapping[str, Any]]:
        return {t: notes.get(t, {"status": "unavailable"}) for t in tickers}

    return resolve


def _available(tone: str, score: float) -> dict[str, Any]:
    return {"status": "available", "tone": tone, "score": score, "article_count": 3}


# Market ----------------------------------------------------------------------
def test_index_technicals_from_rising_closes() -> None:
    start = date(2025, 11, 1)
    closes = [(start + timedelta(days=i), 100.0 + i * 0.5) for i in range(260)]

    entry = briefing.index_technicals("S&P 500", closes)

    assert entry["status"] == "available"
    assert entry["index"] == "S&P 500"
    assert entry["regime_pass"] is True
    assert entry["sma_200"] is not None
    # Volume-derived fields are omitted for indices.
    assert "obv" not in entry and "vol_ratio_50" not in entry


def test_index_technicals_unavailable_with_too_few_closes() -> None:
    closes = [(date(2026, 11, 1) + timedelta(days=i), 100.0) for i in range(10)]

    entry = briefing.index_technicals("Nasdaq 100", closes)

    assert entry == {"index": "Nasdaq 100", "status": "unavailable", "closes": 10}


# Sectors ---------------------------------------------------------------------
def test_sector_breadth_shares_and_unknown_bucket(db_session: Session) -> None:
    a = _asset(db_session, "AAA")
    b = _asset(db_session, "BBB")
    c = _asset(db_session, "CCC")
    unknown = _asset(db_session, "UNK", sector=None)
    snaps = {
        a.id: _indicator(db_session, a, gate=True, regime=True, rsi=60),
        b.id: _indicator(db_session, b, gate=True, regime=True, rsi=50),
        c.id: _indicator(db_session, c, gate=False, regime=False, rsi=40),
    }

    rows = briefing.sector_breadth([a, b, c, unknown], snaps)

    tech = next(r for r in rows if r["sector"] == "technology")
    assert tech["equities"] == 3
    assert tech["with_indicators"] == 3
    assert tech["gate_pass_share"] == pytest.approx(2 / 3, abs=1e-4)
    assert tech["regime_pass_share"] == pytest.approx(2 / 3, abs=1e-4)
    assert tech["avg_rsi_14"] == pytest.approx(50.0)
    unk = next(r for r in rows if r["sector"] == "unknown")
    assert unk["equities"] == 1
    assert unk["with_indicators"] == 0
    assert unk["gate_pass_share"] is None
    # Larger sectors first.
    assert rows[0]["sector"] == "technology"


def test_sector_news_tone_aggregates_available_signals(db_session: Session) -> None:
    a = _asset(db_session, "AAA")
    b = _asset(db_session, "BBB")
    e = _asset(db_session, "EEE", sector="energy")
    notes = {
        "AAA": _available("positive", 0.6),
        "BBB": _available("negative", -0.2),
        "EEE": {"status": "unavailable"},
    }

    tone = briefing.sector_news_tone([a, b, e], notes)

    assert tone["status"] == "available"
    assert tone["sectors"] == [
        {
            "sector": "technology",
            "tickers_with_news": 2,
            "avg_score": pytest.approx(0.2),
            "positive": 1,
            "neutral": 0,
            "negative": 1,
        }
    ]


def test_sector_news_tone_unavailable_without_signals(db_session: Session) -> None:
    a = _asset(db_session, "AAA")

    assert briefing.sector_news_tone([a], {"AAA": {"status": "unavailable"}}) == {
        "status": "unavailable"
    }


def test_candidate_rows_mark_missing_inputs(db_session: Session) -> None:
    a = _asset(db_session, "AAA")
    b = _asset(db_session, "BBB")
    snaps = {a.id: _indicator(db_session, a, gate=True, regime=True, rsi=61.234)}

    rows = briefing.candidate_rows([b, a], snaps, {"AAA": _available("positive", 0.4)})

    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]
    assert rows[0]["gate_pass"] is True
    assert rows[0]["rsi_14"] == 61.2
    assert rows[0]["news"] == {"tone": "positive", "score": 0.4}
    assert rows[1]["indicators"] == "unavailable"
    assert rows[1]["news"] == "unavailable"


# Assembly --------------------------------------------------------------------
def test_build_briefing_end_to_end(db_session: Session) -> None:
    aapl = _asset(db_session, "AAPL")
    _asset(db_session, "XOM", sector="energy")
    _indicator(db_session, aapl, gate=True, regime=True, rsi=55)
    start = date(2025, 10, 1)
    for i in range(260):
        db_session.add(
            BenchmarkPrice(
                benchmark="SP500",
                price_date=start + timedelta(days=i),
                close=5_000.0 + i,
            )
        )
    db_session.flush()
    orchestrator = orchestrator_service.create_orchestrator(
        db_session, label="Core", capital=10_000.0
    )
    orchestrator.free_capital -= 3_000.0
    bot = bot_service.create_bot_session(
        db_session,
        preset_key="rsi_mean_reversion_algo16",
        tickers=["AAPL"],
        initial_capital=3_000.0,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )

    result = briefing.build_briefing(
        db_session,
        orchestrator,
        now=_NOW,
        resolve_sentiment=_sentiment({"AAPL": _available("positive", 0.5)}),
    )

    json.dumps(result)  # JSON-serialisable as stored on the run
    market = {m["index"]: m["status"] for m in result["market"]}
    assert market == {
        "S&P 500": "available",
        "Nasdaq-100": "unavailable",
        "Russell 2000": "unavailable",
    }
    assert {r["sector"] for r in result["sectors"]["breadth"]} == {
        "technology",
        "energy",
    }
    assert result["sectors"]["news_tone"]["status"] == "available"
    assert [c["ticker"] for c in result["candidates"]] == ["AAPL", "XOM"]
    assert len(result["presets"]) >= 8
    running = result["running_bots"]
    assert len(running) == 1
    assert running[0]["bot_id"] == str(bot.id)
    assert running[0]["preset_key"] == "rsi_mean_reversion_algo16"
    assert running[0]["tickers"] == ["AAPL"]
    assert running[0]["allocated_capital"] == 3_000.0
    assert running[0]["current_value"] == 3_000.0
    assert running[0]["total_return_pct"] == 0.0
    assert result["liquidating_bots"] == []
    limits = result["limits"]
    assert limits["free_capital"] == 7_000.0
    assert limits["orchestrator_value"] == 10_000.0
    assert limits["open_slots"] == 2
    assert limits["max_bot_capital"] == 5_000.0
    assert limits["min_bot_capital"] == 1_000.0
