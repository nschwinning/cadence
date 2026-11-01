"""Value objects for the news-sentiment capability.

These are frozen dataclasses (NOT ORM models): the sentiment signal is computed
on demand during a rebalance and cached in process keyed by ``(ticker, date)``,
so nothing is persisted to the database. ``NewsItem`` is what the news source
yields, ``SentimentScore`` is one scored text's tone probabilities, and
``SentimentSignal`` is the resolved per-ticker aggregate the rebalance flow
attaches to the agent's candidates and holdings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from cadence.news_sentiment.constants import SentimentStatus, SentimentTone


@dataclass(frozen=True)
class NewsItem:
    """A single news item for a ticker, as returned by the news source."""

    ticker: str
    headline: str
    summary: str | None
    published_at: datetime

    def text(self) -> str:
        """The text scored for tone (headline, plus summary when present)."""
        if self.summary:
            return f"{self.headline}. {self.summary}"
        return self.headline


@dataclass(frozen=True)
class SentimentScore:
    """Per-text tone class probabilities returned by the scorer."""

    positive: float
    neutral: float
    negative: float

    @property
    def polarity(self) -> float:
        """The item's ``positive − negative`` leaning in ``[-1.0, 1.0]``."""
        return self.positive - self.negative


@dataclass(frozen=True)
class SentimentSignal:
    """The resolved per-ticker aggregate tone block for one ``(ticker, date)``.

    ``status`` records whether a usable signal was produced; when ``AVAILABLE`` the
    ``tone``/``score``/``article_count`` describe the recency-weighted aggregate.
    ``unavailable`` degrades every other field so a consumer can mark the ticker
    without ever reading a fabricated figure.
    """

    ticker: str
    status: SentimentStatus
    as_of: date
    tone: SentimentTone | None = None
    score: float | None = None
    article_count: int = 0

    @classmethod
    def unavailable(cls, ticker: str, as_of: date) -> SentimentSignal:
        """A no-data result carrying only the ticker and as-of date."""
        return cls(ticker=ticker, status=SentimentStatus.UNAVAILABLE, as_of=as_of)

    def annotation(self) -> dict[str, Any]:
        """The compact per-ticker block handed to the rebalance agent.

        An unavailable signal yields the explicit ``{"status": "unavailable"}``
        marker — never an invented tone — so the agent prompt tolerates absence.
        """
        if self.status is not SentimentStatus.AVAILABLE or self.tone is None:
            return {"status": SentimentStatus.UNAVAILABLE.value}
        return {
            "status": SentimentStatus.AVAILABLE.value,
            "tone": self.tone.value,
            "score": round(self.score, 4) if self.score is not None else None,
            "article_count": self.article_count,
            "as_of": self.as_of.isoformat(),
        }
