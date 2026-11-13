"""Tests for the per-ticker recent-headlines helper (no network)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from cadence.config import Settings
from cadence.news_sentiment.constants import MARKET_TZ
from cadence.news_sentiment.models import NewsItem
from cadence.news_sentiment.news import AlpacaNewsSource, news_symbol, recent_headlines

_TODAY = date(2026, 11, 13)


def _item(ticker: str, hours_ago: int, headline: str, source: str | None = "Reuters") -> NewsItem:
    return NewsItem(
        ticker=ticker,
        headline=headline,
        summary=None,
        published_at=datetime(2026, 11, 13, 12, tzinfo=MARKET_TZ) - timedelta(hours=hours_ago),
        source=source,
    )


class _FakeSource:
    def __init__(self, news: dict[str, list[NewsItem]], *, raise_for: str | None = None) -> None:
        self._news = news
        self._raise_for = raise_for
        self.calls: list[tuple[str, datetime, int]] = []

    def fetch_news(self, ticker: str, *, start: datetime, limit: int) -> list[NewsItem]:
        self.calls.append((ticker, start, limit))
        if ticker == self._raise_for:
            raise RuntimeError("boom")
        return self._news.get(ticker, [])


def test_settings_defaults() -> None:
    fields = Settings.model_fields
    assert fields["NEWS_HEADLINES_PER_TICKER"].default == 3
    assert fields["NEWS_HEADLINES_WINDOW_DAYS"].default == 3


def test_newest_headlines_per_ticker() -> None:
    source = _FakeSource(
        {
            "NVDA": [
                _item("NVDA", 30, "Older"),
                _item("NVDA", 1, "Nvidia CEO Jensen Huang resigns"),
                _item("NVDA", 5, "Board names interim CEO", source=None),
                _item("NVDA", 50, "Oldest"),
            ]
        }
    )

    result = recent_headlines(
        ["NVDA", "AAPL"], as_of=_TODAY, per_ticker=3, window_days=3, source=source
    )

    assert list(result) == ["NVDA"]  # AAPL has none: omitted
    assert [h["headline"] for h in result["NVDA"]] == [
        "Nvidia CEO Jensen Huang resigns",
        "Board names interim CEO",
        "Older",
    ]
    assert result["NVDA"][0] == {
        "headline": "Nvidia CEO Jensen Huang resigns",
        "source": "Reuters",
        "published_at": "2026-11-13T11:00:00-05:00",
    }
    assert "source" not in result["NVDA"][1]
    # One request per ticker, window start 3 days back, limit = per_ticker.
    assert sorted(call[0] for call in source.calls) == ["AAPL", "NVDA"]
    assert {call[1].date() for call in source.calls} == {date(2026, 11, 10)}
    assert {call[2] for call in source.calls} == {3}


def test_crypto_tickers_use_the_news_symbol_form() -> None:
    assert news_symbol("BTC-USD") == "BTCUSD"
    assert news_symbol("eth/usd") == "ETHUSD"
    assert news_symbol("AAPL") == "AAPL"
    source = _FakeSource({"BTCUSD": [_item("BTCUSD", 2, "Bitcoin rallies")]})

    result = recent_headlines(["BTC-USD"], as_of=_TODAY, per_ticker=2, source=source)

    assert result == {"BTC-USD": [result["BTC-USD"][0]]}
    assert result["BTC-USD"][0]["headline"] == "Bitcoin rallies"


def test_a_failing_ticker_does_not_fail_the_others() -> None:
    source = _FakeSource({"MSFT": [_item("MSFT", 1, "ok")]}, raise_for="NVDA")
    result = recent_headlines(["NVDA", "MSFT"], as_of=_TODAY, per_ticker=3, source=source)
    assert list(result) == ["MSFT"]


@pytest.mark.parametrize("tickers", [[], [""]])
def test_nothing_to_fetch(tickers: list[str]) -> None:
    source = _FakeSource({})
    assert recent_headlines(tickers, as_of=_TODAY, per_ticker=3, source=source) == {}
    assert source.calls == []


def test_zero_disables_without_fetching() -> None:
    source = _FakeSource({"NVDA": [_item("NVDA", 1, "x")]})
    assert recent_headlines(["NVDA"], as_of=_TODAY, per_ticker=0, source=source) == {}
    assert source.calls == []


def test_duplicate_tickers_fetch_once() -> None:
    source = _FakeSource({})
    recent_headlines(["NVDA", "NVDA"], as_of=_TODAY, per_ticker=3, source=source)
    assert len(source.calls) == 1


def test_alpaca_parse_keeps_the_source() -> None:
    items = AlpacaNewsSource._parse(
        "NVDA",
        {
            "news": [
                {
                    "headline": "Nvidia CEO resigns",
                    "created_at": "2026-11-12T14:00:00Z",
                    "source": "benzinga",
                },
                {"headline": "No source", "created_at": "2026-11-12T13:00:00Z"},
            ]
        },
    )
    assert [(i.headline, i.source) for i in items] == [
        ("Nvidia CEO resigns", "benzinga"),
        ("No source", None),
    ]
