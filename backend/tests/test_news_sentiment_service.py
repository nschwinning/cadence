"""Unit tests for the news-sentiment package (no DB, no network).

Covers the provider contracts (the stub satisfies the Protocols, the real HTTP
client degrades without raising), the settings defaults and the empty-URL disable,
the recency-weighted aggregation / classification bands / determinism / cache
reuse, and the graceful-degradation paths (unset URL, unreachable, scoring error,
no news, partial batch).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from tests.fakes import FakeNewsSource, FakeSentimentScorer

from cadence.config import settings
from cadence.news_sentiment import service
from cadence.news_sentiment.constants import MARKET_TZ, SentimentStatus, SentimentTone
from cadence.news_sentiment.models import NewsItem, SentimentScore
from cadence.news_sentiment.news import AlpacaNewsSource, NewsSource
from cadence.news_sentiment.scorer import HttpSentimentScorer, SentimentScorer

_AS_OF = date(2026, 1, 15)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    service.clear_signal_cache()


def _item(ticker: str, day: date, *, headline: str = "news") -> NewsItem:
    return NewsItem(
        ticker=ticker,
        headline=headline,
        summary=None,
        published_at=datetime(day.year, day.month, day.day, tzinfo=MARKET_TZ),
    )


def _score(pos: float, neg: float) -> SentimentScore:
    return SentimentScore(positive=pos, neutral=round(1.0 - pos - neg, 4), negative=neg)


# --------------------------------------------------------------------------- #
# 2.2 Provider contracts
# --------------------------------------------------------------------------- #


def test_stubs_satisfy_protocols() -> None:
    assert isinstance(FakeSentimentScorer(), SentimentScorer)
    assert isinstance(FakeNewsSource(), NewsSource)


def test_http_scorer_degrades_when_url_unset() -> None:
    # Empty base URL: no network call, returns [] (feature off) rather than raising.
    scorer = HttpSentimentScorer("")
    assert scorer.score(["anything"]) == []


def test_http_scorer_degrades_when_unreachable() -> None:
    # A refused connection degrades to [] (no raise), with a tight timeout.
    scorer = HttpSentimentScorer("http://127.0.0.1:1", timeout=0.25)
    assert scorer.score(["headline about AAPL"]) == []


def test_alpaca_news_source_degrades_without_credentials() -> None:
    source = AlpacaNewsSource(api_key="", secret_key="")
    start = datetime(2026, 1, 12, tzinfo=MARKET_TZ)
    assert source.fetch_news("AAPL", start=start, limit=10) == []


# --------------------------------------------------------------------------- #
# 2.3 Settings
# --------------------------------------------------------------------------- #


def test_sentiment_settings_defaults() -> None:
    assert settings.SENTIMENT_SERVICE_URL == ""
    assert settings.SENTIMENT_WINDOW_DAYS == 3
    assert settings.SENTIMENT_RECENCY_HALFLIFE_DAYS == 1.5
    assert settings.SENTIMENT_NEUTRAL_BAND == 0.15


def test_empty_service_url_disables_feature() -> None:
    # No scorer injected + empty URL => every ticker unavailable, no network.
    result = service.resolve_sentiment_annotations(
        ["AAPL", "MSFT"], as_of=_AS_OF
    )
    assert result["AAPL"] == {"status": "unavailable"}
    assert result["MSFT"] == {"status": "unavailable"}


# --------------------------------------------------------------------------- #
# 2.4 Aggregation, classification, determinism, cache
# --------------------------------------------------------------------------- #


def test_classification_bands() -> None:
    neutral = service.aggregate_signal(
        "T", [_item("T", _AS_OF)], [_score(0.40, 0.35)], _AS_OF
    )
    assert neutral.tone is SentimentTone.NEUTRAL

    positive = service.aggregate_signal(
        "T", [_item("T", _AS_OF)], [_score(0.70, 0.10)], _AS_OF
    )
    assert positive.tone is SentimentTone.POSITIVE

    negative = service.aggregate_signal(
        "T", [_item("T", _AS_OF)], [_score(0.10, 0.70)], _AS_OF
    )
    assert negative.tone is SentimentTone.NEGATIVE


def test_aggregate_weights_recent_news_more() -> None:
    # A very positive item today and an equally negative item a week ago. With
    # recency weighting the aggregate leans positive, not ~0 (the equal-weight mean).
    items = [_item("T", _AS_OF), _item("T", date(2026, 1, 8))]
    scores = [_score(0.9, 0.05), _score(0.05, 0.9)]
    signal = service.aggregate_signal("T", items, scores, _AS_OF)
    assert signal.status is SentimentStatus.AVAILABLE
    assert signal.article_count == 2
    assert signal.score is not None and signal.score > 0.2
    assert signal.tone is SentimentTone.POSITIVE


def test_aggregate_mismatched_lengths_unavailable() -> None:
    signal = service.aggregate_signal(
        "T", [_item("T", _AS_OF)], [], _AS_OF
    )
    assert signal.status is SentimentStatus.UNAVAILABLE


def test_resolution_is_deterministic_and_cached() -> None:
    scorer = FakeSentimentScorer(default=_score(0.7, 0.1))
    source = FakeNewsSource(by_ticker={"AAPL": [_item("AAPL", _AS_OF)]})
    first = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    second = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert first == second
    assert first["AAPL"]["status"] == "available"
    assert first["AAPL"]["tone"] == "positive"
    # Cache reuse within the same (ticker, date): the scorer ran exactly once.
    assert len(scorer.score_calls) == 1


# --------------------------------------------------------------------------- #
# 2.5 Graceful degradation
# --------------------------------------------------------------------------- #


def test_no_news_degrades() -> None:
    scorer = FakeSentimentScorer()
    source = FakeNewsSource(by_ticker={})
    result = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert result["AAPL"] == {"status": "unavailable"}
    assert scorer.score_calls == []  # no news => never scored


def test_scorer_error_degrades() -> None:
    scorer = FakeSentimentScorer(error=RuntimeError("sidecar down"))
    source = FakeNewsSource(by_ticker={"AAPL": [_item("AAPL", _AS_OF)]})
    result = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert result["AAPL"] == {"status": "unavailable"}


def test_scorer_empty_result_degrades() -> None:
    scorer = FakeSentimentScorer(empty=True)
    source = FakeNewsSource(by_ticker={"AAPL": [_item("AAPL", _AS_OF)]})
    result = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert result["AAPL"] == {"status": "unavailable"}


def test_news_source_error_degrades() -> None:
    scorer = FakeSentimentScorer()
    source = FakeNewsSource(error=ConnectionError("news down"))
    result = service.resolve_sentiment_annotations(
        ["AAPL"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert result["AAPL"] == {"status": "unavailable"}


def test_partial_availability_batch() -> None:
    scorer = FakeSentimentScorer(default=_score(0.7, 0.1))
    source = FakeNewsSource(by_ticker={"AAPL": [_item("AAPL", _AS_OF)]})
    result = service.resolve_sentiment_annotations(
        ["AAPL", "MSFT"], scorer=scorer, news_source=source, as_of=_AS_OF
    )
    assert result["AAPL"]["status"] == "available"
    assert result["MSFT"] == {"status": "unavailable"}
