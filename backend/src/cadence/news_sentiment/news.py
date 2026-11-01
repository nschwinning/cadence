"""News retrieval behind a thin, testable Protocol.

All network access to the news source is confined to :class:`AlpacaNewsSource`.
The rest of the domain depends only on the :class:`NewsSource` protocol, so tests
inject a stub and never touch the network. Retrieval is best-effort: an unset
credential, an unreachable source, or a malformed response yields an empty list
rather than raising, so the aggregation above it degrades to "sentiment
unavailable".
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import httpx

from cadence.config import settings
from cadence.news_sentiment.constants import MARKET_TZ
from cadence.news_sentiment.models import NewsItem

logger = logging.getLogger(__name__)


@runtime_checkable
class NewsSource(Protocol):
    """Seam for fetching recent news items for a ticker over a trailing window.

    Implemented by :class:`AlpacaNewsSource` in production and by a fake in tests.
    ``fetch_news`` is synchronous and NEVER raises: a failed fetch returns an empty
    list, which the caller treats as "no usable sentiment". Items are returned
    newest first.
    """

    def fetch_news(
        self, ticker: str, *, start: datetime, limit: int
    ) -> list[NewsItem]:
        """Return the source's news for ``ticker`` since ``start`` (never raises)."""
        ...


class AlpacaNewsSource:
    """Production :class:`NewsSource` backed by the Alpaca News API.

    Reuses the Alpaca credentials. Confines all HTTP to this class and never
    raises: any failure (missing credentials, connection error, bad status, or a
    malformed body) degrades to an empty list and is logged.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        secret_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base_url = (
            base_url if base_url is not None else settings.ALPACA_NEWS_BASE_URL
        ).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.ALPACA_API_KEY
        self._secret_key = (
            secret_key if secret_key is not None else settings.ALPACA_SECRET_KEY
        )
        self._timeout = (
            timeout
            if timeout is not None
            else settings.SENTIMENT_SERVICE_TIMEOUT_SECONDS
        )

    def fetch_news(
        self, ticker: str, *, start: datetime, limit: int
    ) -> list[NewsItem]:
        if not self._api_key or not self._secret_key:
            return []
        try:
            response = httpx.get(
                self._base_url,
                params={
                    "symbols": ticker,
                    "start": start.isoformat(),
                    "limit": limit,
                    "sort": "desc",
                },
                headers={
                    "APCA-API-KEY-ID": self._api_key,
                    "APCA-API-SECRET-KEY": self._secret_key,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("news fetch failed for %s: %s", ticker, exc)
            return []
        return self._parse(ticker, payload)

    @staticmethod
    def _parse(ticker: str, payload: object) -> list[NewsItem]:
        """Map the Alpaca response into news items, skipping unparseable rows."""
        rows = payload.get("news") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            published = _parse_timestamp(row.get("created_at"))
            headline = row.get("headline")
            if published is None or not isinstance(headline, str) or not headline:
                continue
            summary = row.get("summary")
            items.append(
                NewsItem(
                    ticker=ticker,
                    headline=headline,
                    summary=summary if isinstance(summary, str) and summary else None,
                    published_at=published,
                )
            )
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items


def _parse_timestamp(raw: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``), or ``None``."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MARKET_TZ)
    return parsed


def window_start(as_of: date, window_days: int) -> datetime:
    """The inclusive start of the trailing window as a market-tz datetime."""
    start_date = as_of - timedelta(days=max(window_days, 0))
    return datetime(
        start_date.year, start_date.month, start_date.day, tzinfo=MARKET_TZ
    )
